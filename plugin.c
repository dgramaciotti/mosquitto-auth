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
int check_command_permission(const char *username, const char *topic);

struct plugin_data {
    char *config_file;
    char *user_auth_url;
    char *acl_auth_url;
};

static int perform_auth_request(const char *url, const char *username, const char *json_body)
{
    CURL *curl;
    CURLcode res;
    long http_code = 0;
    int success = 0;

    curl = curl_easy_init();
    if(curl) {
        struct curl_slist *headers = NULL;
        char auth_header[1024];

        snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s", username ? username : "");

        headers = curl_slist_append(headers, "Content-Type: application/json");
        headers = curl_slist_append(headers, "User-Agent: mosquitto");
        headers = curl_slist_append(headers, auth_header);

        curl_easy_setopt(curl, CURLOPT_URL, url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L); // avoid blocking broker forever

        res = curl_easy_perform(curl);
        if(res == CURLE_OK) {
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            if(http_code == 200) {
                success = 1;
            } else {
                mosquitto_log_printf(MOSQ_LOG_ERR, "Auth service responded with HTTP %ld", http_code);
            }
        } else {
            mosquitto_log_printf(MOSQ_LOG_ERR, "CURL error: %s", curl_easy_strerror(res));
        }

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }

    return success;
}

// Required: Plugin version check
mosq_plugin_EXPORT int mosquitto_plugin_version(int supported_version_count, const int *supported_versions)
{
    // Return 5 for v5 interface
    return 5;
}

// Required: Plugin initialization
mosq_plugin_EXPORT int mosquitto_plugin_init(mosquitto_plugin_id_t *identifier, void **user_data, struct mosquitto_opt *options, int option_count)
{
    struct plugin_data *data;
    
    // Allocate plugin data
    data = malloc(sizeof(struct plugin_data));
    if (!data) {
        return MOSQ_ERR_NOMEM;
    }
    
    // Initialize data structure
    memset(data, 0, sizeof(struct plugin_data));
    *user_data = data;
    
    // Parse configuration options
    for (int i = 0; i < option_count; i++) {
        if (!strcmp(options[i].key, "config_file")) {
        data->config_file = strdup(options[i].value);
        } else if (!strcmp(options[i].key, "user_auth_url")) {
            data->user_auth_url = strdup(options[i].value);
        } else if (!strcmp(options[i].key, "acl_auth_url")) {
            data->acl_auth_url = strdup(options[i].value);
        }
        // Add more configuration parsing here
    }

    mosquitto_log_printf(MOSQ_LOG_INFO, "config_file: %s", data->config_file);
    mosquitto_log_printf(MOSQ_LOG_INFO, "user_auth_url: %s", data->user_auth_url);
    mosquitto_log_printf(MOSQ_LOG_INFO, "acl_auth_url: %s", data->acl_auth_url);
    
    // Register callbacks for authentication and ACL
    mosquitto_callback_register(identifier, MOSQ_EVT_BASIC_AUTH, cb_basic_auth, NULL, data);
    mosquitto_callback_register(identifier, MOSQ_EVT_ACL_CHECK, cb_acl_check, NULL, data);
    
    // Optional: Register for extended auth, TLS-PSK, etc.
    // mosquitto_callback_register(identifier, MOSQ_EVT_EXT_AUTH_START, cb_ext_auth_start, NULL, data);
    
    return MOSQ_ERR_SUCCESS;
}

// Required: Plugin cleanup
mosq_plugin_EXPORT int mosquitto_plugin_cleanup(void *user_data, struct mosquitto_opt *options, int option_count)
{
    struct plugin_data *data = (struct plugin_data*)user_data;
    
    if (data) {
        if (data->config_file) free(data->config_file);
        if (data->user_auth_url) free(data->user_auth_url);
        if (data->acl_auth_url) free(data->acl_auth_url);
        free(data);
    }
    
    return MOSQ_ERR_SUCCESS;
}

// Callback: Basic username/password authentication
int cb_basic_auth(int event, void *event_data, void *user_data)
{
    struct mosquitto_evt_basic_auth *evt = (struct mosquitto_evt_basic_auth*)event_data;
    struct plugin_data *data = (struct plugin_data*)user_data;

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
    struct mosquitto_evt_acl_check *evt = (struct mosquitto_evt_acl_check*)event_data;
    struct plugin_data *data = (struct plugin_data*)user_data;

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
    if(!url) return 0;

    char json_body[512];
    snprintf(json_body, sizeof(json_body),
             "{ \"username\": \"%s\", \"password\": \"%s\", \"client_id\": \"%s\" }",
             username ? username : "",
             password ? password : "",
             client_id ? client_id : "");

    return perform_auth_request(url, username, json_body);
}

// ACL check against external service
int check_acl_permission(const char *username, const char *client_id, const char *topic, int access, const char *url)
{
    if(!url) return 0;

    char json_body[512];
    snprintf(json_body, sizeof(json_body),
             "{ \"username\": \"%s\", \"client_id\": \"%s\", \"topic\": \"%s\", \"access\": %d }",
             username ? username : "",
             client_id ? client_id : "",
             topic ? topic : "",
             access);

    return perform_auth_request(url, username, json_body);
}

int check_command_permission(const char *username, const char *topic)
{
    // Custom logic for command topic permissions
    return 1;
}