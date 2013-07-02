#!/usr/bin/env bash

# Adds user to the sudoers file so they can do everything w/o a pass
# Some binaries might be under /sbin or /usr/sbin, so make sure sudo will
# see them by forcing PATH
host_name=`hostname`
echo "127.0.0.1 ${host_name}" >> /etc/hosts

TEMPFILE=`mktemp`
echo "GUEST_USERNAME ALL=(ALL) NOPASSWD:ALL" > $TEMPFILE
chmod 0440 $TEMPFILE
sudo chown root:root $TEMPFILE
sudo mv $TEMPFILE /etc/sudoers.d/60_trove_guest

# Some installs have issues with the user homedir
sudo chown GUEST_USERNAME /home/GUEST_USERNAME

# Copies all the trove code to the guest image
sudo -u GUEST_USERNAME rsync -e'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' HOST_USERNAME@NETWORK_GATEWAY:PATH_TROVE/ /home/GUEST_USERNAME/trove

# Do an apt-get update since its SUPER slow first time
apt-get update

# Disable AppArmor so that trove guestagent can change the conf
# TODO this should probably be done in the guest and then re-enabled install
ln -s /etc/apparmor.d/usr.sbin.mysqld /etc/apparmor.d/disable/
apparmor_parser -R /etc/apparmor.d/usr.sbin.mysqld

# Starts the trove guestagent (using the upstart script)
service trove-guest start
