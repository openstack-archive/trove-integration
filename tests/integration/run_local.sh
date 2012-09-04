#!/usr/bin/env bash
# Specify the path to the RDL repo as argument one.
# This script will create a .pid file and report in the current directory.

set -e
if [ $# -lt 1 ]; then
    echo "Please give the path to the RDL repo as argument one."
    exit 5
else
    RDL_PATH=$1
fi
if [ $# -lt 2 ]; then
    echo "Please give the path to the RD Client as argument two."
    exit 5
else
    RDC_PATH=$2
fi
shift;
shift;


PID_FILE="`pwd`.pid"

function start_server() {
    pushd $RDL_PATH
    bin/start_server.sh --pid_file=$PID_FILE
    popd
}

function stop_server() {
    if [ -f $PID_FILE ];
    then
        pushd $RDL_PATH
        bin/stop_server.sh $PID_FILE
        popd
    else
        echo "The pid file did not exist, so not stopping server."
    fi
}
function on_error() {
    echo "Something went wrong!"
    stop_server
}

trap on_error EXIT  # Proceed to trap - END in event of failure.

start_server
REDDWARF_CLIENT_PATH=$RDC_PATH tox -e local -- $@
stop_server


trap - EXIT
echo "Ran tests successfully. :)"
exit 0
