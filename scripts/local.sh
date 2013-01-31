#!/usr/bin/env bash

# local.sh to install reddwarf
# Install and start Reddwarf (DBaaS) service

# Dependencies:
# - functions

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace

# Import common functions from devstack dir
# Destination path for installation ``DEST``
DEST=${DEST:-/opt/stack}
TOP_DIR=$(cd $(dirname "$0") && pwd)
source $TOP_DIR/functions
source $TOP_DIR/lib/database
source $TOP_DIR/stackrc
source $TOP_DIR/localrc
ENABLED_SERVICES+=,reddwarf,rd-api,rd-tmgr

# Public facing bits
SERVICE_HOST=${SERVICE_HOST:-localhost}
SERVICE_PROTOCOL=${SERVICE_PROTOCOL:-http}
NETWORK_GATEWAY=${NETWORK_GATEWAY:-10.0.0.1}
KEYSTONE_AUTH_HOST=${KEYSTONE_AUTH_HOST:-$SERVICE_HOST}
KEYSTONE_AUTH_PROTOCOL=${KEYSTONE_AUTH_PROTOCOL:-$SERVICE_PROTOCOL}
KEYSTONE_AUTH_PORT=${KEYSTONE_AUTH_PORT:-35357}
OS_USER=${OS_USER:-admin}
OS_TENANT=${OS_TENANT:-admin}
DATABASE_HOST=${DATABASE_HOST:-localhost}
DATABASE_USER=${DATABASE_USER:-root}
DATABASE_PASSWORD=${DATABASE_PASSWORD:-$MYSQL_PASSWORD}
BASE_SQL_CONN=${BASE_SQL_CONN:-${DATABASE_TYPE}://$DATABASE_USER:$DATABASE_PASSWORD@$DATABASE_HOST}

# Set up default configuration
REDDWARF_DIR=$DEST/reddwarf/
REDDWARFCLIENT_DIR=$DEST/python-reddwarfclient/
REDDWARF_PACKAGES_DIR=/var/lib/packages/debian/
REDDWARF_BUILD_DIR=/tmp/build/
REDDWARF_INTEGRATION_CONF_DIR=/tmp/reddwarf-integration/
REDDWARF_ENV_CONF_PATH=$REDDWARF_INTEGRATION_CONF_DIR/env.rc
REDDWARF_CONF_DIR=/etc/reddwarf/
REDDWARF_LOCAL_CONF_DIR=$REDDWARF_DIR/etc/reddwarf/
REDDWARF_AUTH_ENDPOINT=$KEYSTONE_AUTH_PROTOCOL://$KEYSTONE_AUTH_HOST:$KEYSTONE_AUTH_PORT/v2.0

# Set Reddwarf interface related configuration
REDDWARF_SERVICE_HOST=${REDDWARF_SERVICE_HOST:-$SERVICE_HOST}
REDDWARF_SERVICE_PORT=${REDDWARF_SERVICE_PORT:-8779}
REDDWARF_SERVICE_PROTOCOL=${REDDWARF_SERVICE_PROTOCOL:-$SERVICE_PROTOCOL}

# reddwarf service git paths
GIT_BASE=https://github.com
REDDWARF_REPO=${GIT_BASE}/stackforge/reddwarf.git
REDDWARF_BRANCH=master
REDDWARFCLIENT_REPO=${GIT_BASE}/stackforge/python-reddwarfclient.git
REDDWARFCLIENT_BRANCH=master

# Support potential entry-points for console scripts
if [ -d $REDDWARF_DIR/bin ] ; then
    REDDWARF_BIN_DIR=$REDDWARF_DIR/bin
else
    REDDWARF_BIN_DIR=/usr/local/bin
fi

###############################################################################
# Misc. tools
###############################################################################

# msgout() - prints message with severity and time to stdout.
function msgout() {
    local level=$1
    local str=$2
    local tm=`date +"%Y-%m-%d %H:%M:%S"`
    if [ $level = "DEBUG" ] && [ -z $VERBOSE ]; then
            return 0
    else
        echo "$tm: $PROG [$$]: $1: $str"
    fi

    return 0
}

function reddwarf_mysql_nova() {
    echo mysql nova --execute "$@"
    mysql -u root -p$DATABASE_PASSWORD nova --execute "$@"
}

function reddwarf_manage() {
    cd $REDDWARF_DIR
    bin/reddwarf-manage --config-file=$REDDWARF_CONF_DIR/reddwarf.conf $@
}

###############################################################################
# Configure Keystone for Reddwarf related helper functions
###############################################################################

function reddwarf_get_attribute_id() {
    keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN $1-list | grep $2 | get_field $3
}

function reddwarf_add_keystone_user() {
    # Adds a user. Prints the UUID to standard out.
    USER_NAME=$1
    USER_PASS=$2
    USER_EMAIL=$3
    USER_TENANT=$4
    # Create the user "reddwarf"
    USER_UUID=`reddwarf_get_attribute_id user $USER_NAME 1`
    if [ -z "$USER_UUID" ]; then
        USER_UUID=$(keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN user-create \
            --name=$USER_NAME \
            --pass=$USER_PASS \
            --email=$USER_EMAIL \
            --tenant_id $USER_TENANT \
            | grep " id " | get_field 2)
    fi
    echo $USER_UUID
}

function reddwarf_create_keystone_user_role() {
    TENANT_UUID=$1
    USER_UUID=$2
    ROLE_UUID=$3
    keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN user-role-add \
        --tenant_id $TENANT_UUID \
        --user_id $USER_UUID \
        --role_id $ROLE_UUID
}

function reddwarf_create() {
    keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN $1-create \
             --name $2 \
             | grep " id " | get_field 2
}

function reddwarf_configure_keystone() {
    msgout "DEBUG" "Configuring keystone..."
    # Create the "reddwarf" tenant
    # First we should check if these exist
    REDDWARF_TENANT=`reddwarf_get_attribute_id tenant reddwarf 1`
    if [ -z "$REDDWARF_TENANT" ]; then
        REDDWARF_TENANT=$(reddwarf_create tenant reddwarf)
    fi

    # Create the reddwarf role if it doesn't exist.
    # Admin role should already exist
    ADMIN_ROLE=`reddwarf_get_attribute_id role admin 1`
    REDDWARF_ROLE=`reddwarf_get_attribute_id role reddwarf 1`
    if [ -z "$REDDWARF_ROLE" ]; then
        REDDWARF_ROLE=$(reddwarf_create role reddwarf)
    fi

    REDDWARF_USER=$(reddwarf_add_keystone_user reddwarf REDDWARF-PASS reddwarf@example.com $REDDWARF_TENANT)
    reddwarf_create_keystone_user_role $REDDWARF_TENANT $REDDWARF_USER $REDDWARF_ROLE

    RADMIN_USER=$(reddwarf_add_keystone_user radmin radmin radmin@example.com $REDDWARF_TENANT)
    reddwarf_create_keystone_user_role $REDDWARF_TENANT $RADMIN_USER $REDDWARF_ROLE
    reddwarf_create_keystone_user_role $REDDWARF_TENANT $RADMIN_USER $ADMIN_ROLE

    mkdir -p ${REDDWARF_INTEGRATION_CONF_DIR}
    touch $REDDWARF_ENV_CONF_PATH
    iniset $REDDWARF_ENV_CONF_PATH DEFAULT REDDWARF_TENANT $REDDWARF_TENANT
    iniset $REDDWARF_ENV_CONF_PATH DEFAULT REDDWARF_USER $REDDWARF_USER
    iniset $REDDWARF_ENV_CONF_PATH DEFAULT REDDWARF_ROLE $REDDWARF_ROLE

    # Now attempt a login to check it's working
    curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' \
     -H "Content-type: application/json" $REDDWARF_AUTH_ENDPOINT/tokens

    # Register reddwarf service.
    REDDWARF_SERVICE_UUID=$(keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN service-list | grep "reddwarf" | get_field 1)
    if [ -z $REDDWARF_SERVICE_UUID ]; then
        REDDWARF_SERVICE_UUID=$(keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN service-create \
            --name=Reddwarf \
            --type=reddwarf \
            --description="Reddwarf Database Service" \
            | grep " id " | get_field 2)
        keystone --endpoint $REDDWARF_AUTH_ENDPOINT --token $SERVICE_TOKEN endpoint-create \
            --region RegionOne \
            --service_id $REDDWARF_SERVICE_UUID \
            --publicurl "$REDDWARF_SERVICE_PROTOCOL://$REDDWARF_SERVICE_HOST:$REDDWARF_SERVICE_PORT/v1.0/\$(tenant_id)s" \
            --adminurl "$REDDWARF_SERVICE_PROTOCOL://$REDDWARF_SERVICE_HOST:$REDDWARF_SERVICE_PORT/v1.0/\$(tenant_id)s" \
            --internalurl "$REDDWARF_SERVICE_PROTOCOL://$REDDWARF_SERVICE_HOST:$REDDWARF_SERVICE_PORT/v1.0/\$(tenant_id)s"
    fi
}

###############################################################################
# Setup Reddwarf Config file and related functions
###############################################################################

function fix_rd_configfile() {
    # Create the reddwarf conf dir if it doesn't exist
    sudo mkdir -p ${REDDWARF_CONF_DIR}
    sudo chown -R $USER: ${REDDWARF_CONF_DIR}

    # Copy conf files over to the reddwarf conf dir
    cd $REDDWARF_DIR
    cp etc/reddwarf/reddwarf.conf.sample $REDDWARF_CONF_DIR/reddwarf.conf
    cp etc/reddwarf/api-paste.ini $REDDWARF_CONF_DIR/api-paste.ini
    cp etc/reddwarf/reddwarf-taskmanager.conf.sample $REDDWARF_CONF_DIR/reddwarf-taskmanager.conf

    # Figure out the db connection urls
    local dburl
    database_connection_url dburl reddwarf

    # Fix the tokens in the conf files
    iniset $REDDWARF_CONF_DIR/reddwarf.conf DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $REDDWARF_CONF_DIR/reddwarf.conf DEFAULT sql_connection $dburl
    iniset $REDDWARF_CONF_DIR/api-paste.ini filter:tokenauth admin_token $SERVICE_TOKEN

    iniset $REDDWARF_CONF_DIR/reddwarf-taskmanager.conf DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $REDDWARF_CONF_DIR/reddwarf-taskmanager.conf DEFAULT sql_connection $dburl
    iniset $REDDWARF_CONF_DIR/reddwarf-taskmanager.conf filter:tokenauth admin_token $SERVICE_TOKEN

    iniset $REDDWARF_LOCAL_CONF_DIR/reddwarf-guestagent.conf.sample DEFAULT rabbit_password $RABBIT_PASSWORD
    sed -i "s/e1a2c042c828d3566d0a/$ADMIN_PASSWORD/g" $REDDWARF_LOCAL_CONF_DIR/reddwarf-guestagent.conf.sample
    sed -i "s/10.0.0.1/$NETWORK_GATEWAY/g" $REDDWARF_LOCAL_CONF_DIR/reddwarf-guestagent.conf.sample
}

###############################################################################
# Adding new flavours to nova and related functions
###############################################################################

function add_flavor() {
    local mod="add_flavor"
    msgout "DEBUG" "$mod<-- $FLAVOR_ID ($FLAVOR_NAME), memory=$FLAVOR_MEMORY_MB, root_gb=$FLAVOR_ROOT_GB VCPUS=$5"
    FLAVOR_NAME=$1
    FLAVOR_ID=$2
    FLAVOR_MEMORY_MB=$3
    FLAVOR_ROOT_GB=$4
    FLAVOR_VCPUS=$5

    if [[ -z $(nova --os-username=$OS_USER --os-password=$ADMIN_PASSWORD --os-tenant-name=$OS_TENANT --os-auth-url=$REDDWARF_AUTH_ENDPOINT flavor-list | grep $FLAVOR_NAME) ]]; then
        nova --os-username=$OS_USER --os-password=$ADMIN_PASSWORD --os-tenant-name=$OS_TENANT --os-auth-url=$REDDWARF_AUTH_ENDPOINT flavor-create $FLAVOR_NAME $FLAVOR_ID $FLAVOR_MEMORY_MB $FLAVOR_ROOT_GB $FLAVOR_VCPUS
    fi
    msgout "DEBUG" "$mod:-->"
}

function add_flavors() {
    local mod="add_flavors"
    msgout "DEBUG" "$mod<-- "
    # Incredibly useful for testing resize in a VM.
    set +e
    add_flavor 'tinier' 6 506 10 1
    # It can also be useful to have a flavor with 512 megs and a bit of disk space.
    add_flavor 'm1.rd-tiny' 7 512 2 1
    # It's also useful to have a flavor that is slightly bigger than tiny but smaller than small...
    add_flavor 'm1.rd-smaller' 8 768 2 1
    set -e
    msgout "DEBUG" "$mod:-->"
}

###############################################################################
# stack.sh entry points
###############################################################################

# cleanup_reddwarfclient() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_reddwarfclient() {
    local mod="cleanup_reddwarfclient"
    # This function intentionally left blank
    msgout "DEBUG" "$mod:<-- "
    msgout "DEBUG" "$mod:--> "
}

# cleanup_reddwarf() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_reddwarf() {
    local mod="cleanup_reddwarf"
    # This function intentionally left blank
    msgout "DEBUG" "$mod:<-- "
    msgout "DEBUG" "$mod:--> "
}

# configure_reddwarfclient() - Set config files, create data dirs, etc
function configure_reddwarfclient() {
    local mod="configure_reddwarfclient"
    msgout "DEBUG" "$mod<-- "
    setup_develop $REDDWARFCLIENT_DIR
    msgout "DEBUG" "$mod:-->"
}

# configure_reddwarf() - Set config files, create data dirs, etc
function configure_reddwarf() {
    local mod="configure_reddwarf"
    msgout "DEBUG" "$mod<-- ($REDDWARF_DIR)"

    install_package libxslt1-dev python-pexpect
    setup_develop $REDDWARF_DIR

    # Create the reddwarf build dir if it doesn't exist
    sudo mkdir -p ${REDDWARF_BUILD_DIR}
    sudo chown -R $USER: ${REDDWARF_BUILD_DIR}

    msgout "DEBUG" "$mod:-->"
}

# install_reddwarfclient() - Collect source and prepare
function install_reddwarfclient() {
    local mod="install_reddwarfclient"
    msgout "DEBUG" "$mod<-- "
    git_clone $REDDWARFCLIENT_REPO $REDDWARFCLIENT_DIR $REDDWARFCLIENT_BRANCH
    msgout "DEBUG" "$mod:-->"
}

# install_reddwarf() - Collect source and prepare
function install_reddwarf() {
    local mod="install_reddwarf"
    msgout "DEBUG" "$mod<-- "
    git_clone $REDDWARF_REPO $REDDWARF_DIR $REDDWARF_BRANCH
    msgout "DEBUG" "$mod:-->"
}

# init_reddwarf() - Initializes Reddwarf Database as a Service
function init_reddwarf() {
    local mod="init_reddwarf"
    msgout "DEBUG" "$mod<-- "

    msgout "DEBUG" "(Re)Creating reddwarf db..."
    recreate_database reddwarf utf8

    mkdir -p $REDDWARF_INTEGRATION_CONF_DIR

    msgout "DEBUG" "Creating Keystone users..."
    reddwarf_configure_keystone

    msgout "DEBUG" "Making a temporary reddwarf config file..."
    fix_rd_configfile

    msgout "DEBUG" "Initializing the Reddwarf Database..."
    reddwarf_manage db_sync

    msgout "DEBUG" "Adding reddwarf specific flavours..."
    add_flavors

    msgout "DEBUG" "$mod:-->"
}

# start_reddwarf() - Start running processes, including screen
function start_reddwarf() {
    local mod="start_reddwarf"
    msgout "DEBUG" "$mod<-- "
    screen_it rd-api "cd $REDDWARF_DIR; bin/reddwarf-api --config-file=$REDDWARF_CONF_DIR/reddwarf.conf | tee $REDDWARF_CONF_DIR/reddwarf-api.log"
    screen_it rd-tmgr "cd $REDDWARF_DIR; bin/reddwarf-taskmanager --config-file=$REDDWARF_CONF_DIR/reddwarf-taskmanager.conf | tee $REDDWARF_CONF_DIR/reddwarf-taskmanager.log"
    msgout "DEBUG" "$mod:-->"
}

function devstack_post_install_hook() {
    install_reddwarf
    install_reddwarfclient
    configure_reddwarf
    configure_reddwarfclient
    init_reddwarf
    start_reddwarf
}

devstack_post_install_hook

# Restore xtrace
$XTRACE
