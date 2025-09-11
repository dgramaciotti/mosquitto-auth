#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mosquitto.h>
#include <mosquitto_broker.h>
#include <mosquitto_plugin.h>
#include <curl/curl.h>

int cb_basic_auth(int event, void *event_data, void *user_data);
int cb_acl_check(int event, void *event_data, void *user_data);

int authenticate_user(const char *username, const char *password, const char *client_id, const char *url);
int check_acl_permission(const char *username, const char *client_id, const char *topic, int access, const char *url);

struct plugin_data {
    char *user_auth_url;
    char *acl_auth_url;
};

static mosquitto_plugin_id_t *plg_id = NULL;

// Helper function to escape JSON strings
static char* json_escape_string(const char *input)
{
    if (!input) return mosquitto_strdup("");
    
    size_t len = strlen(input);
    size_t escaped_len = len * 2 + 1; // Worst case: every char needs escaping
    char *escaped = mosquitto_malloc(escaped_len);
    if (!escaped) return NULL;
    
    size_t i = 0, j = 0;
    while (i < len && j < escaped_len - 1) {
        switch (input[i]) {
            case '"':
            case '\\':
                escaped[j++] = '\\';
                escaped[j++] = input[i];
                break;
            case '\b':
                escaped[j++] = '\\';
                escaped[j++] = 'b';
                break;
            case '\f':
                escaped[j++] = '\\';
                escaped[j++] = 'f';
                break;
            case '\n':
                escaped[j++] = '\\';
                escaped[j++] = 'n';
                break;
            case '\r':
                escaped[j++] = '\\';
                escaped[j++] = 'r';
                break;
            case '\t':
                escaped[j++] = '\\';
                escaped[j++] = 't';
                break;
            default:
                escaped[j++] = input[i];
                break;
        }
        i++;
    }
    escaped[j] = '\0';
    return escaped;
}

// Helper function to clean up plugin_data
static void cleanup_plugin_data(struct plugin_data *data)
{
    if (data) {
        if (data->user_auth_url) {
            mosquitto_free(data->user_auth_url);
            data->user_auth_url = NULL;
        }
        if (data->acl_auth_url) {
            mosquitto_free(data->acl_auth_url);
            data->acl_auth_url = NULL;
        }
        mosquitto_free(data);
    }
}

// Does an auth request to the provided urls in the config file
// Authorization header contains the username as a token (jwt). Password is not used because the acl check
// doesnt provide the password as an option.
static int perform_auth_request(const char *url, const char *username, const char *json_body)
{
    CURL *curl;
    CURLcode res;
    long http_code = 0;
    int success = 0;

    if (!url || !json_body) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Invalid parameters for auth request");
        return 0;
    }

    curl = curl_easy_init();
    if (!curl) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Failed to initialize CURL");
        return 0;
    }

    struct curl_slist *headers = NULL;
    char auth_header[1024];
    
    int header_len = snprintf(auth_header, sizeof(auth_header), 
                             "Authorization: Bearer %s", username ? username : "");
    
    if (header_len >= sizeof(auth_header)) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Username too long for auth header.");
        curl_easy_cleanup(curl);
        return 0;
    }

    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, "User-Agent: mosquitto-client");
    headers = curl_slist_append(headers, auth_header);

    if (!headers) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Failed to create HTTP headers");
        curl_easy_cleanup(curl);
        return 0;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    res = curl_easy_perform(curl);
    if (res == CURLE_OK) {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
        if (http_code == 200) {
            success = 1;
        } else {
            mosquitto_log_printf(MOSQ_LOG_ERR, "Auth service responded with HTTP %ld", http_code);
        }
    } else {
        mosquitto_log_printf(MOSQ_LOG_ERR, "CURL error: %s", curl_easy_strerror(res));
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    return success;
}

mosq_plugin_EXPORT int mosquitto_plugin_version(int supported_version_count, const int *supported_versions)
{
    return 5; // Return 5 for v5 interface
}

mosq_plugin_EXPORT int mosquitto_plugin_init(mosquitto_plugin_id_t *identifier, void **user_data, struct mosquitto_opt *options, int option_count)
{
    int rc;
    struct plugin_data *data;
    
    if (!identifier || !user_data || !options) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Invalid initialization parameters or auth urls not provided.");
        return MOSQ_ERR_INVAL;
    }
    
    data = mosquitto_malloc(sizeof(struct plugin_data));
    if (!data) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Out of memory allocating plugin data");
        return MOSQ_ERR_NOMEM;
    }
    
    memset(data, 0, sizeof(struct plugin_data));
    *user_data = data;
    
    // Parse configuration options
    for (int i = 0; i < option_count; i++) {
        if (!options[i].key) continue;
        
        if (strcmp(options[i].key, "user_auth_url") == 0) {
            data->user_auth_url = mosquitto_strdup(options[i].value);
            if (!data->user_auth_url) {
                mosquitto_log_printf(MOSQ_LOG_ERR, "Out of memory duplicating user_auth_url");
                cleanup_plugin_data(data);
                return MOSQ_ERR_NOMEM;
            }
        } else if (strcmp(options[i].key, "acl_auth_url") == 0) {
            data->acl_auth_url = mosquitto_strdup(options[i].value);
            if (!data->acl_auth_url) {
                mosquitto_log_printf(MOSQ_LOG_ERR, "Out of memory duplicating acl_auth_url");
                cleanup_plugin_data(data);
                return MOSQ_ERR_NOMEM;
            }
        }
    }

    plg_id = identifier;
    
    // Register basic auth callback
    rc = mosquitto_callback_register(identifier, MOSQ_EVT_BASIC_AUTH, cb_basic_auth, NULL, data);
    if (rc != MOSQ_ERR_SUCCESS) {
        const char *error_msg;
        switch (rc) {
            case MOSQ_ERR_ALREADY_EXISTS:
                error_msg = "mosquitto-auth plugin can only be loaded once";
                break;
            case MOSQ_ERR_NOMEM:
                error_msg = "out of memory";
                break;
            default:
                error_msg = "unexpected error registering basic auth callback";
                break;
        }
        mosquitto_log_printf(MOSQ_LOG_ERR, "Error: %s", error_msg);
        cleanup_plugin_data(data);
        return rc;
    }
    
    // Register ACL check callback
    rc = mosquitto_callback_register(identifier, MOSQ_EVT_ACL_CHECK, cb_acl_check, NULL, data);
    if (rc != MOSQ_ERR_SUCCESS) {
        const char *error_msg;
        switch (rc) {
            case MOSQ_ERR_ALREADY_EXISTS:
                error_msg = "mosquitto-auth plugin can only be loaded once";
                break;
            case MOSQ_ERR_NOMEM:
                error_msg = "out of memory";
                break;
            default:
                error_msg = "unexpected error registering ACL callback";
                break;
        }
        mosquitto_log_printf(MOSQ_LOG_ERR, "Error: %s", error_msg);
        
        // Cleanup: unregister the first callback
        mosquitto_callback_unregister(identifier, MOSQ_EVT_BASIC_AUTH, cb_basic_auth, NULL);
        cleanup_plugin_data(data);
        return rc;
    }
    
    mosquitto_log_printf(MOSQ_LOG_INFO, "mosquitto-auth plugin initialized successfully");
    return MOSQ_ERR_SUCCESS;
}

mosq_plugin_EXPORT int mosquitto_plugin_cleanup(void *user_data, struct mosquitto_opt *options, int option_count)
{
    struct plugin_data *data = (struct plugin_data*)user_data;
    
    if (plg_id) {
        mosquitto_callback_unregister(plg_id, MOSQ_EVT_BASIC_AUTH, cb_basic_auth, NULL);
        mosquitto_callback_unregister(plg_id, MOSQ_EVT_ACL_CHECK, cb_acl_check, NULL);
    }
    
    cleanup_plugin_data(data);
    
    mosquitto_log_printf(MOSQ_LOG_INFO, "mosquitto-auth plugin cleaned up");
    return MOSQ_ERR_SUCCESS;
}

// Improved callback for MQTT auth
int cb_basic_auth(int event, void *event_data, void *user_data)
{
    if (!event_data || !user_data) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Invalid parameters in basic auth callback");
        return MOSQ_ERR_AUTH;
    }

    struct mosquitto_evt_basic_auth *evt = (struct mosquitto_evt_basic_auth*)event_data;
    struct plugin_data *data = (struct plugin_data*)user_data;

    if (!evt->client) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "No client in auth event");
        return MOSQ_ERR_AUTH;
    }

    const char *username = evt->username;
    const char *password = evt->password;
    const char *client_id = mosquitto_client_id(evt->client);

    mosquitto_log_printf(MOSQ_LOG_INFO, "Auth attempt: client=%s, username=%s",
                         client_id ? client_id : "NULL",
                         username ? username : "NULL");

    if (authenticate_user(username, password, client_id, data->user_auth_url)) {
        return MOSQ_ERR_SUCCESS;
    } else {
        return MOSQ_ERR_AUTH;
    }
}

// Callback: Access Control List (ACL) check
int cb_acl_check(int event, void *event_data, void *user_data)
{
    if (!event_data || !user_data) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Invalid parameters in ACL check callback");
        return MOSQ_ERR_ACL_DENIED;
    }

    struct mosquitto_evt_acl_check *evt = (struct mosquitto_evt_acl_check*)event_data;
    struct plugin_data *data = (struct plugin_data*)user_data;

    if (!evt->client) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "No client in ACL event");
        return MOSQ_ERR_ACL_DENIED;
    }

    const char *username = mosquitto_client_username(evt->client);
    const char *client_id = mosquitto_client_id(evt->client);
    const char *topic = evt->topic;
    int access = evt->access;

    mosquitto_log_printf(MOSQ_LOG_INFO, "ACL check: client=%s, username=%s, topic=%s, access=%d",
                         client_id ? client_id : "NULL",
                         username ? username : "NULL",
                         topic ? topic : "NULL",
                         access);

    if (check_acl_permission(username, client_id, topic, access, data->acl_auth_url)) {
        return MOSQ_ERR_SUCCESS;
    } else {
        return MOSQ_ERR_ACL_DENIED;
    }
}

int authenticate_user(const char *username, const char *password, const char *client_id, const char *url)
{
    if (!url) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "No auth URL configured");
        return 0;
    }

    // Escape JSON strings to prevent injection
    char *escaped_username = json_escape_string(username);
    char *escaped_password = json_escape_string(password);
    char *escaped_client_id = json_escape_string(client_id);
    
    if (!escaped_username || !escaped_password || !escaped_client_id) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Failed to escape JSON strings in auth");
        if (escaped_username) mosquitto_free(escaped_username);
        if (escaped_password) mosquitto_free(escaped_password);
        if (escaped_client_id) mosquitto_free(escaped_client_id);
        return 0;
    }

    char json_body[1024];
    int json_len = snprintf(json_body, sizeof(json_body),
                           "{ \"username\": \"%s\", \"password\": \"%s\", \"client_id\": \"%s\" }",
                           escaped_username, escaped_password, escaped_client_id);
    
    mosquitto_free(escaped_username);
    mosquitto_free(escaped_password);
    mosquitto_free(escaped_client_id);
    
    if (json_len >= sizeof(json_body)) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "JSON body too large for auth request");
        return 0;
    }

    return perform_auth_request(url, username, json_body);
}

int check_acl_permission(const char *username, const char *client_id, const char *topic, int access, const char *url)
{
    if (!url) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "No ACL URL configured");
        return 0;
    }

    // Escape JSON strings to prevent injection
    char *escaped_username = json_escape_string(username);
    char *escaped_client_id = json_escape_string(client_id);
    char *escaped_topic = json_escape_string(topic);
    
    if (!escaped_username || !escaped_client_id || !escaped_topic) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "Failed to escape JSON strings in ACL check");
        if (escaped_username) mosquitto_free(escaped_username);
        if (escaped_client_id) mosquitto_free(escaped_client_id);
        if (escaped_topic) mosquitto_free(escaped_topic);
        return 0;
    }

    char json_body[1024];
    int json_len = snprintf(json_body, sizeof(json_body),
                           "{ \"username\": \"%s\", \"client_id\": \"%s\", \"topic\": \"%s\", \"access\": %d }",
                           escaped_username, escaped_client_id, escaped_topic, access);
    
    mosquitto_free(escaped_username);
    mosquitto_free(escaped_client_id);
    mosquitto_free(escaped_topic);
    
    if (json_len >= sizeof(json_body)) {
        mosquitto_log_printf(MOSQ_LOG_ERR, "JSON body too large for ACL request");
        return 0;
    }

    return perform_auth_request(url, username, json_body);
}