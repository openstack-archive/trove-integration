#!/usr/bin/env bash

# Adds user to the sudoers file so they can do everything w/o a pass
# Some binaries might be under /sbin or /usr/sbin, so make sure sudo will
# see them by forcing PATH
TEMPFILE=`mktemp`
echo "GUEST_USERNAME ALL=(ALL) NOPASSWD:ALL" > $TEMPFILE
chmod 0440 $TEMPFILE
sudo chown root:root $TEMPFILE
sudo mv $TEMPFILE /etc/sudoers.d/60_reddwarf_guest

# Copies all the reddwarf code to the guest image
sudo -u GUEST_USERNAME rsync -e'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' HOST_USERNAME@NETWORK_GATEWAY:PATH_REDDWARF/ /home/GUEST_USERNAME/reddwarf

# Do an apt-get update since its SUPER slow first time
apt-get update

# Add extras which is _only_ in pip.....
pip install extras

# Disable AppArmor so that reddwarf guestagent can change the conf
# TODO this should probably be done in the guest and then re-enabled install
ln -s /etc/apparmor.d/usr.sbin.mysqld /etc/apparmor.d/disable/
apparmor_parser -R /etc/apparmor.d/usr.sbin.mysqld

# Starts the reddwarf guestagent (using the upstart script)
service reddwarf-guest start
