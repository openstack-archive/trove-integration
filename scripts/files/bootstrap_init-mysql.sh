#!/usr/bin/env bash

# Copies all the reddwarf code to the guest image
sudo -u USERNAME rsync -e'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' 10.0.0.1:PATH_REDDWARF/ /home/USERNAME/reddwarf
# Adds user to the sudoers file so they can do everything w/o a pass
echo 'USERNAME ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers
# Do an apt-get update since its SUPER slow first time
apt-get update
# Starts the reddwarf guestagent (using the upstart script)
service reddwarf-guest start
