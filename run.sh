#!/bin/bash

# Constants
TRUE_VALUE="yes"  # true/false global variables are set using this. idk how to write bash, sorry.
FALSE_VALUE="no"
BACKEND_ENV_FILE="backend/app/configs/.env"
FRONTEND_ENV_FILE="frontend/.env.local"

# Globals (TBD by user)
FRONTEND_URL=""
BACKEND_URL=""

SEND_EMAILS=""
SMTP_SERVER=""
SMTP_PORT=""
SMTP_USERNAME=""
SMTP_PASSWORD=""

MYSQL_ROOT_PASSWORD=""

USE_TTS="$FALSE_VALUE"

USE_OPENAI=""
OPENAI_KEY=""

USE_OLLAMA=""
OLLAMA_URL=""
OLLAMA_LMS="[]"
OLLAMA_EMBEDS="[]"

USE_OPENAI_COMPATIBLE=""
OPENAI_COMPATIBLE_URL=""
OPENAI_COMPATIBLE_LMS="[]"
OPENAI_COMPATIBLE_EMBEDS="[]"
OPENAI_COMPATIBLE_TTS="[]"
OPENAI_COMPATIBLE_KEY=""

USE_ANTHROPIC=""
ANTHROPIC_KEY=""

USE_MATHPIX=""
MATHPIX_APP=""
MATHPIX_KEY=""

USE_ELEVEN_LABS=""
ELEVEN_LABS_KEY=""

USE_WEB=""
BING_KEY=""

USE_SEARXNG=""
SEARXNG_URL=""

USE_GOOGLE_AUTH=""
GOOGLE_AUTH_CLIENT_ID=""
GOOGLE_AUTH_CLIENT_SECRET=""

USE_GITHUB_AUTH=""
GITHUB_AUTH_CLIENT_ID=""
GITHUB_AUTH_CLIENT_SECRET=""

USE_KEYCLOAK_AUTH=""
KEYCLOAK_CLIENT_SECRET=""
KEYCLOAK_CLIENT_ID=""
KEYCLOAK_REALM=""
KEYCLOAK_HOST=""

JWT_SECRET=""
REFRESH_SECRET=""

run() {
    # Initialize variables
    MY_BUILD_ENV="prod"
    build_flag=""
    PYTHONUNBUFFERED="false"

    # Iterate over all arguments
    for arg in "$@"; do
        case $arg in
            --dev)
                MY_BUILD_ENV="dev"
                ;;
            --build)
                build_flag="--build"
                ;;
        esac
    done

    if [ "$MY_BUILD_ENV" = "dev" ]; then
        PYTHONUNBUFFERED="true"
    fi

    # This is the for the root mysql password
    source ".env"

    # Construct the docker-compose command
    cmd="MY_BUILD_ENV=$MY_BUILD_ENV PYTHONUNBUFFERED=$PYTHONUNBUFFERED docker-compose"
    
    if is_email_enabled; then
        cmd+=" --profile email"
    fi
    
    cmd+=" up $build_flag"

    # Execute the command
    echo "Executing: $cmd"
    eval "$cmd"
}

# Checks if set up by seeing if there's a backend ENV file written.
check_if_set_up() {
    if [[ -f $BACKEND_ENV_FILE ]]; then
        return 0  # True, setup is complete
    fi
    return 1  # False, setup is not complete
}

record_setup_complete(){
    echo "$TRUE_VALUE" > "$SETUP_STATUS_FILE"
}

do_setup() {
    configure_url
    configure_email
    configure_db
    configure_ai
    configure_search_engine
    configure_auth

    export_backend_env
    export_frontend_env
    export_root_env

    return 0  # Return 0 to indicate success
}

# Function to ask a yes/no question
ask_yes_no() {
    local prompt="$1"
    local response
    while true; do
        read -rp "$prompt (y/n):`echo $'\n> '`" response
        case "$response" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo "Please answer yes or no ('y' or 'n')." ;;
        esac
    done
}

# Function to ask for a credential
ask_credential() {
    local prompt="$1"
    local response
    read -rp "$prompt:`echo $'\n> '`" response
    echo "$response"
}

generate_password() {
    local length=15
    local charset="A-Za-z0-9"
    local password=$(LC_ALL=C tr -dc "$charset" < /dev/urandom | head -c $length)
    echo "$password"
}

configure_url() {
    echo "When Abbey runs altogether on your machine inside docker containers, those containers expose port 3000 for the frontend, and port 5000 for the backend, by default."
    FRONTEND_URL=$(ask_credential "What FULL public-facing URL will your machine use for the frontend? Ex: https://my-frontend.com or http://localhost:3000 if just used locally.")
    BACKEND_URL=$(ask_credential "What FULL public-facing URL will your machine use for the backend? Ex: https://my-backend.com or http://localhost:5000 if just used locally.")
}

configure_email() {
    if ask_yes_no "Do you want to let Abbey send emails? You'll need an SMTP server (email)."; then
        SEND_EMAILS=$TRUE_VALUE
        echo "OK, please provide your email credentials for SMTP"
        
        SMTP_SERVER=$(ask_credential "SMTP Server")
        SMTP_PORT=$(ask_credential "SMTP Port")
        SMTP_USERNAME=$(ask_credential "SMTP Username (email)")
        SMTP_PASSWORD=$(ask_credential "SMTP Password")
    else
        SEND_EMAILS=$FALSE_VALUE
    fi
}

configure_db() {    
    # Make MySQL root password
    MYSQL_ROOT_PASSWORD=$(generate_password)
}

configure_auth() {
    # What auth providers would you like to use?
    # What are your client ids / client secrets
    
    echo "Abbey relies on 3rd party OAuth2 authentication providers, like Google. You need to have a client ID and client secret for each OAuth provider you wish to configure."
    echo "Abbey supports Google, GitHub, and Keycloak. You only have to configure a provider if you're using Abbey in a multi-user setting."
    
    if ask_yes_no "Would you like to configure Google OAuth2?"; then
        USE_GOOGLE_AUTH=$TRUE_VALUE
        GOOGLE_AUTH_CLIENT_ID=$(ask_credential "Please provide a Google client ID")
        GOOGLE_AUTH_CLIENT_SECRET=$(ask_credential "Please provide a Google client secret")
    else
        USE_GOOGLE_AUTH=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure GitHub OAuth2?"; then
        USE_GITHUB_AUTH=$TRUE_VALUE
        GITHUB_AUTH_CLIENT_ID=$(ask_credential "Please provide a GitHub client ID")
        GITHUB_AUTH_CLIENT_SECRET=$(ask_credential "Please provide a GitHub client secret")
    else
        USE_GITHUB_AUTH=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure KeyCloak OAuth2?"; then
        USE_KEYCLOAK_AUTH=$TRUE_VALUE
        KEYCLOAK_CLIENT_ID=$(ask_credential "Please provide a Keycloak client ID")
        KEYCLOAK_REALM=$(ask_credential "Please provide a Keycloak realm")
        KEYCLOAK_CLIENT_SECRET=$(ask_credential "Please provide a Keycloak client secret")
        KEYCLOAK_HOST=$(ask_credential "Please provide a Keycloak host (like https://my-keycloak.com)")
    else
        USE_KEYCLOAK_AUTH=$FALSE_VALUE
    fi

    JWT_SECRET=$(generate_password)
    REFRESH_SECRET=$(generate_password)
}

add_model_to_json() {
    local json_array=$1
    local model_entry=$2

    if [ "$json_array" = "[]" ]; then
        json_array="["
    else
        json_array="${json_array%]}"
        json_array="${json_array},"
    fi

    json_array="${json_array}${model_entry}]"

    echo "$json_array"
}

configure_ai() {
    # What ai providers would you like to use?
    # What are your keys?
    echo "To use Abbey, you will need to configure some AI providers, like the OpenAI API."
    echo "Note that you will need to configure at least one language model and one embeddings model."
    if ask_yes_no "Would you like to configure the OpenAI API?"; then
        USE_OPENAI=$TRUE_VALUE
        USE_TTS=$TRUE_VALUE
        OPENAI_KEY=$(ask_credential "OK, please provide an OpenAI API key")
    else
        USE_OPENAI=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure Ollama to run local models?"; then
        USE_OLLAMA=$TRUE_VALUE
        echo "If you're running Ollama on the same machine as Abbey, it's available at http://host.docker.internal:11434. If you're running it on another machine, it might be https://example.com or something."
        OLLAMA_URL=$(ask_credential "Please provide the Ollama URL")

        while ask_yes_no "Do you want to add an Ollama language model? Note that you must have these models already pulled."; do
            model_code=$(ask_credential "Enter language model code (like 'llama3.2')")
            context_length=$(ask_credential "Enter context length (default 4096)")
            vision_support=$(ask_yes_no "Does this model support vision?")

            # Convert vision support to boolean
            vision_boolean="false"
            if [ "$vision_support" = "y" ]; then
                vision_boolean="true"
            fi

            model_entry="{\"code\": \"$model_code\", \"context_length\": ${context_length:-4096}, \"vision\": $vision_boolean}"
            OLLAMA_LMS=$(add_model_to_json "$OLLAMA_LMS" "$model_entry")
        done

        # Collect embedding models
        while ask_yes_no "Do you want to add an embedding model? Note that you must have these models already pulled."; do
            model_code=$(ask_credential "Enter embedding model code")
            
            model_entry="{\"code\": \"$model_code\"}"
            OLLAMA_EMBEDS=$(add_model_to_json "$OLLAMA_EMBEDS" "$model_entry")
        done

        if [ "$OLLAMA_EMBEDS" = "[]" ]; then
            if [ "$USE_OPENAI" = "$FALSE_VALUE" ]; then
                echo "You must configure at least one embedding model from OpenAI or Ollama! Exiting."
                exit 1
            fi
        fi

    else
        USE_OLLAMA=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure an OpenAI Compatible API (like LocalAI, LMStudio, etc.)?"; then
        USE_OPENAI_COMPATIBLE=$TRUE_VALUE
        echo "If you're running the API on the same machine as Abbey, it's available at http://host.docker.internal:1234, with 1234 replaced by the appropriate port. If you're running it on another machine, it might be https://example.com or something."
        OPENAI_COMPATIBLE_URL=$(ask_credential "Please provide the full API URL")
        OPENAI_COMPATIBLE_KEY=$(ask_credential "Please provide your API key, if any is required")

        while ask_yes_no "Do you want to add an API language model?"; do
            model_code=$(ask_credential "Enter language model code (like 'llama-3.2-3b-instruct')")
            context_length=$(ask_credential "Enter context length (default 8192)")
            vision_support=$(ask_yes_no "Does this model support vision?")

            # Convert vision support to boolean
            vision_boolean="false"
            if [ "$vision_support" = "y" ]; then
                vision_boolean="true"
            fi

            model_entry="{\"code\": \"$model_code\", \"context_length\": ${context_length:-8192}, \"vision\": $vision_boolean}"
            OPENAI_COMPATIBLE_LMS=$(add_model_to_json "$OPENAI_COMPATIBLE_LMS" "$model_entry")
        done

        # Collect embedding models
        while ask_yes_no "Do you want to add an API embedding model?"; do
            model_code=$(ask_credential "Enter embedding model code")
            
            model_entry="{\"code\": \"$model_code\"}"
            OPENAI_COMPATIBLE_EMBEDS=$(add_model_to_json "$OPENAI_COMPATIBLE_EMBEDS" "$model_entry")
        done

        # Collect TTS 
        while ask_yes_no "Do you want to add an API text-to-speech model?"; do
            model_code=$(ask_credential "Enter voice code (i.e., 'onyx')")
            model_entry="{\"voice\": \"$model_code\"}"
            OPENAI_COMPATIBLE_TTS=$(add_model_to_json "$OPENAI_COMPATIBLE_TTS" "$model_entry")
        done
    else
        USE_OPENAI_COMPATIBLE=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure the Anthropic API?"; then
        USE_ANTHROPIC=$TRUE_VALUE
        ANTHROPIC_KEY=$(ask_credential "OK, please provide an Anthropic API key")
    else
        USE_ANTHROPIC=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure the Mathpix API for OCR?"; then
        USE_MATHPIX=$TRUE_VALUE
        MATHPIX_APP=$(ask_credential "OK, please provide a Mathpix App Name")
        MATHPIX_KEY=$(ask_credential "OK, please provide a Mathpix API key")
    else
        USE_MATHPIX=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to configure Eleven Labs for text-to-speech?"; then
        USE_ELEVEN_LABS=$TRUE_VALUE
        USE_TTS=$TRUE_VALUE
        ELEVEN_LABS_KEY=$(ask_credential "OK, please provide an Eleven Labs API key")
    else
        USE_ELEVEN_LABS=$FALSE_VALUE
    fi

    echo "AI configuration completed."
}

configure_search_engine() {
    # Would you like to use bing?
    # What is your bing API key?
    if ask_yes_no "Would you like to use the Bing API to allow Abbey to search the web?"; then
        USE_WEB=$TRUE_VALUE
        BING_KEY=$(ask_credential "OK, please provide a Bing API key")
    else
        USE_WEB=$FALSE_VALUE
    fi

    if ask_yes_no "Would you like to connect a SearXNG instance (note: must have format json enabled)?"; then
        USE_SEARXNG=$TRUE_VALUE
        echo "If you're running SearXNG on the same machine as Abbey, it's probably available at http://host.docker.internal:8080. If you're running it on another machine, it might be https://example.com or something."
        SEARXNG_URL=$(ask_credential "OK, please provide the URL")
    else
        USE_SEARXNG=$FALSE_VALUE
    fi
}

# Needs to be run AFTER setup complete / affirmed (because it loads in environment variables which could mess with stuff)
is_email_enabled() {
    # Load the environment variables from BACKEND_ENV_FILE
    if [[ -f "$BACKEND_ENV_FILE" ]]; then
        # Source the environment file to load variables
        source "$BACKEND_ENV_FILE"
    fi

    # Check if either SMTP_SERVER or SENDGRID_API_KEY is set
    if [[ -n "$SMTP_SERVER" || -n "$SENDGRID_API_KEY" ]]; then
        return 0  # True: Email is enabled
    else
        return 1  # False: Email is not enabled
    fi
}

export_backend_env() {
    # Create or overwrite the .env file
    {

        echo "FRONTEND_URL=\"$FRONTEND_URL\""

        if [ "$SEND_EMAILS" = "$TRUE_VALUE" ]; then
            echo "SMTP_SERVER=\"$SMTP_SERVER\""
            echo "SMTP_PORT=\"$SMTP_PORT\""
            echo "SMTP_EMAIL=\"$SMTP_USERNAME\""
            echo "SMTP_PASSWORD=\"$SMTP_PASSWORD\""
        fi

        if [ "$USE_OPENAI" = "$TRUE_VALUE" ]; then
            echo "OPENAI_API_KEY=\"$OPENAI_KEY\""
        fi

        if [ "$USE_ANTHROPIC" = "$TRUE_VALUE" ]; then
            echo "ANTHROPIC_API_KEY=\"$ANTHROPIC_KEY\""
        fi

        if [ "$USE_MATHPIX" = "$TRUE_VALUE" ]; then
            echo "MATHPIX_API_APP=\"$MATHPIX_APP\""
            echo "MATHPIX_API_KEY=\"$MATHPIX_KEY\""
        fi

        if [ "$USE_ELEVEN_LABS" = "$TRUE_VALUE" ]; then
            echo "ELEVEN_LABS_API_KEY=\"$ELEVEN_LABS_KEY\""
        fi

        if [ "$USE_WEB" = "$TRUE_VALUE" ]; then
            echo "BING_API_KEY=\"$BING_KEY\""
        fi

        if [ "$USE_SEARXNG" = "$TRUE_VALUE" ]; then
            echo "SEARXNG_URL=\"$SEARXNG_URL\""
        fi

        if [ "$USE_OLLAMA" = "$TRUE_VALUE" ]; then
            echo "OLLAMA_URL='$OLLAMA_URL'"
            echo "OLLAMA_LMS='$OLLAMA_LMS'"
            echo "OLLAMA_EMBEDS='$OLLAMA_EMBEDS'"
        fi

        if [ "$USE_OPENAI_COMPATIBLE" = "$TRUE_VALUE" ]; then
            echo "OPENAI_COMPATIBLE_URL='$OPENAI_COMPATIBLE_URL'"
            echo "OPENAI_COMPATIBLE_LMS='$OPENAI_COMPATIBLE_LMS'"
            echo "OPENAI_COMPATIBLE_EMBEDS='$OPENAI_COMPATIBLE_EMBEDS'"
            echo "OPENAI_COMPATIBLE_TTS='$OPENAI_COMPATIBLE_TTS'"
            echo "OPENAI_COMPATIBLE_KEY='$OPENAI_COMPATIBLE_KEY'"
        fi

        echo "DB_ENDPOINT=mysql"  # Hard coded into the docker compose
        echo "DB_USERNAME=root"  # Perhaps not good practice?
        echo "DB_PASSWORD=\"$MYSQL_ROOT_PASSWORD\""
        echo "DB_PORT=3306"
        echo "DB_NAME=learn"
        echo "DB_TYPE=local"

        echo "CUSTOM_AUTH_DB_ENDPOINT=mysql"  # Hard coded into the docker compose
        echo "CUSTOM_AUTH_DB_USERNAME=root"  # Perhaps not good practice?
        echo "CUSTOM_AUTH_DB_PASSWORD=\"$MYSQL_ROOT_PASSWORD\""
        echo "CUSTOM_AUTH_DB_PORT=3306"
        echo "CUSTOM_AUTH_DB_NAME=custom_auth"

        echo "SECRET_KEY=$(generate_password)"
        echo "CUSTOM_AUTH_SECRET=\"$JWT_SECRET\""
    } > "$BACKEND_ENV_FILE"
}

export_frontend_env() {
    {
        if [ "$USE_GOOGLE_AUTH" = "$TRUE_VALUE" ]; then
            echo "NEXT_PUBLIC_ENABLE_GOOGLE_AUTH=1"
            echo "GOOGLE_CLIENT_ID=\"$GOOGLE_AUTH_CLIENT_ID\""
            echo "GOOGLE_SECRET=\"$GOOGLE_AUTH_CLIENT_SECRET\""
        fi

        if [ "$USE_GITHUB_AUTH" = "$TRUE_VALUE" ]; then
            echo "NEXT_PUBLIC_ENABLE_GITHUB_AUTH=1"
            echo "GITHUB_CLIENT_ID=\"$GITHUB_AUTH_CLIENT_ID\""
            echo "GITHUB_SECRET=\"$GITHUB_AUTH_CLIENT_SECRET\""
        fi

        if [ "$USE_KEYCLOAK_AUTH" = "$TRUE_VALUE" ]; then
            echo "NEXT_PUBLIC_ENABLE_KEYCLOAK_AUTH=1"
            echo "KEYCLOAK_CLIENT_ID=\"$KEYCLOAK_CLIENT_ID\""
            echo "KEYCLOAK_REALM=\"$KEYCLOAK_REALM\""
            echo "KEYCLOAK_SECRET=\"$KEYCLOAK_CLIENT_SECRET\""
            echo "KEYCLOAK_PUBLIC_URL=\"$KEYCLOAK_HOST\""
        fi
        
        if [ "$USE_TTS" = "$FALSE_VALUE" ]; then
            echo "NEXT_PUBLIC_HIDE_TTS=1"
        fi

        echo "CUSTOM_AUTH_DB_HOST=mysql"  # Hard coded into the docker compose
        echo "CUSTOM_AUTH_DB_USER=root"  # Perhaps not good practice?
        echo "CUSTOM_AUTH_DB_PASSWORD=\"$MYSQL_ROOT_PASSWORD\""
        echo "CUSTOM_AUTH_DB_PORT=3306"
        echo "CUSTOM_AUTH_DB_NAME=custom_auth"

        echo "NEXT_PUBLIC_BACKEND_URL=\"$BACKEND_URL\""
        echo "NEXT_PUBLIC_ROOT_URL=\"$FRONTEND_URL\""

        echo "NEXT_PUBLIC_AUTH_SYSTEM=custom"  # all self-hosters use custom auth
        echo "NEXT_SERVER_SIDE_BACKEND_URL=http://backend:5000"  # hardcoded into the docker compose

        echo "JWT_SECRET=\"$JWT_SECRET\""
        echo "REFRESH_TOKEN_SECRET=\"$REFRESH_SECRET\""

        if [ "$USE_MATHPIX" = "$FALSE_VALUE" ]; then
            echo "NEXT_PUBLIC_DISABLE_OCR=1"
        fi

        if [ "$USE_WEB" = "$FALSE_VALUE" ]; then
            if [ "$USE_SEARXNG" = "$FALSE_VALUE" ]; then
                echo "NEXT_PUBLIC_DISABLE_WEB=1"
            fi
        fi

        # While clerk is available in the config, there needs to be non blank (even if non functional) keys.
        echo "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=not-a-key"
        echo "CLERK_SECRET_KEY=not-a-key"
        
        echo "CUSTOM_AUTH_DATABASE_ENABLED=1"
        echo "NEXT_PUBLIC_HIDE_COLLECTIONS=1"

    } > "$FRONTEND_ENV_FILE"
}

export_root_env() {
    {
        echo "MYSQL_ROOT_PASSWORD=\"$MYSQL_ROOT_PASSWORD\""
    } > .env
}

# Check if docker-compose is available
if command -v docker-compose >/dev/null 2>&1; then  # If the docker compose command exists
    do_run=false
    if ! check_if_set_up; then
        if do_setup; then
            do_run=true
        fi
    else
        do_run=true
    fi

    if $do_run; then
        run "$@";  # Pass all command line arguments to run function
    fi
else
    echo "docker-compose is not available."
    echo "Please download and install Docker"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Visit: https://docs.docker.com/desktop/install/mac-install/"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Visit: https://docs.docker.com/engine/install/"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        echo "Visit: https://docs.docker.com/desktop/install/windows-install/"
    else
        echo "Please check the Docker website for installation instructions."
    fi
fi
