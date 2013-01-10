## Integration dev scripts, tests and docs for Reddwarf.

***

### Steps to setup this environment:

Install a fresh Ubuntu 12.04 (Precise Pangolin) image ( _We suggest to create a virtual machine_ )

#### Login to the machine as root

#### Make sure we have git installed:

    $ apt-get update
    $ apt-get install git-core -y

#### Add a user that is not root if you do not already have one:

    $ adduser ubuntu
    $ visudo

  add this line to the file below the root user

    ubuntu  ALL=(ALL:ALL) ALL

    **OR use this if you dont want to type your password to sudo a command**

    ubuntu  ALL=(ALL:NOPASSWD) ALL

  if /dev/pts/0 does not have read/write for your user

    $ chmod 660 /dev/pts/0

  *Note that this number can change and if you can not connect to the screen session then the /dev/pts/# needs modding like above.*

#### Login with ubuntu:

    $ su ubuntu
    $ cd ~

#### Clone this repo:

    $ git clone https://github.com/stackforge/reddwarf-integration.git

#### Go into the scripts directory:

    $ cd reddwarf-integration/scripts/

#### Running redstack is the core script:
*Run this to get the command list with a short description of each*

    $ ./redstack

#### Install all the dependencies

    $ ./redstack install

***

#### Connecting to the screen session

    $ screen -x stack

*If that command fails with the error*

    Cannot open your terminal '/dev/pts/1'

*If that command fails with the error chmod the corresponding /dev/pts/#*

    $ chmod 660 /dev/pts/1

#### Detach from the screen session
Allows the services to continue running in the background

    ctrl+a then d

***

#### Kick start the build/initialize/build-image commands
*Add mysql as a parameter to set build and add the mysql guest image*

    $ ./redstack kick-start mysql

#### Start up the reddwarf services in a screen session

    $ ./redstack start

 or, to run outside of a screen:

    $ ./redstack run

***

*Optional commands if you did not run kick-start*

#### Build the packages

    $ ./redstack build

#### Initialize the database and setup everything

    $ ./redstack initalize

#### Build the image and add it to glance

    $ ./redstack build-image mysql

***

#### Running the reddwarf client (It's so easy!)
*This sets of the authorization endpoint and gets a token for you*

    $ ./redstack rd-client

#### Running the nova client (It's so easy!)
*This sets of the authorization endpoint and gets a token for you*

    $ ./redstack nova-client

***

### Reset your environment

#### Stop all the services running in the screens and refresh the envirnoment:

    $ killall -9 screen

    $ RECLONE=yes ./redstack install
    $ ./redstack kick-start mysql
    $ ./redstack start

 or

    $ RECLONE=yes ./redstack install
    $ ./redstack build
    $ ./redstack initialize
    $ ./redstack build-image mysql
    $ ./redstack start

***

### VMware Fusion 5 speed improvement
We found out that if you are running ubuntu with KVM or Qemu it can be extemely slow. We found some ways of making this better with in VMware settings.
On a clean install of ubuntu 12.04 enable these options in VMware. (likey the same in other virutalizing platforms)

1. Shutdown the Ubuntu VM.

2. Go to the VM Settings -> Processors & Memory -> Advanced Options
   Check the "Enable hypervisor applications in this virtual machine"
   There is one other option that may improve your performance overall as well.

3. Go to the VM Settings -> Advanced
   Set the "Troubleshooting" option to "None"

4. I would suggest after setting these create a snapshot so that in cases where things break down you can revert to a clean snapshot.

5. Boot up the VM and run the `./redstack install`

6. To verify that KVM is setup properly after the devstack installation you can run these commands.
```
ubuntu@ubuntu:~$ kvm-ok
INFO: /dev/kvm exists
KVM acceleration can be used
```

