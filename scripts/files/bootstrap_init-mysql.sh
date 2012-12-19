#!/usr/bin/env bash

# Copies all the reddwarf code to the guest image
sudo -u GUEST_USERNAME rsync -e'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' HOST_USERNAME@10.0.0.1:PATH_REDDWARF/ /home/GUEST_USERNAME/reddwarf
# Adds user to the sudoers file so they can do everything w/o a pass
echo 'GUEST_USERNAME ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers.d/rdguest-sudoers
sudo chmod 0440 /etc/sudoers.d/rdguest-sudoers
# Do an apt-get update since its SUPER slow first time
apt-get update
# Add extras which is _only_ in pip.....
pip install extras
# Starts the reddwarf guestagent (using the upstart script)
service reddwarf-guest start
