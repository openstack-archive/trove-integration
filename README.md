## Integration dev scripts, tests and docs for Reddwarf.

***

### Steps to setup this environment:

Install a fresh Ubuntu 11.10 (Oneiric Ocelot) image ( _We suggest to create a virtual machine_ )

#### Login to the machine as root

#### Make sure we have git installed:

    $ apt-get update
    $ apt-get install git-core -y

#### Add a user that is not root if you do not already have one:

    $ adduser ubuntu
    $ visudo

  add this line to the file below the root user

    ubuntu  ALL=(ALL:ALL) ALL

#### Login with ubuntu:

    $ su ubuntu
    $ cd ~

#### Clone this repo:

    $ git clone https://github.com/hub-cap/reddwarf_lite-integration.git

#### Go into the scripts directory:

    $ cd reddwarf_lite-integration/scripts/

#### Running redstack is the core script:
*Run this to get the command list with a short description of each*

    $ ./redstack

#### Install all the dependencies

    $ ./redstack install

***

#### Kick start the build/initialize/build-image/start commands

    $ ./redstack kick-start

***

*Optional commands if you did not run kick-start*

#### Build the packages

    $ ./redstack build

#### Initialize the database and setup everything

    $ ./redstack initalize

#### Build the image and add it to glance

    $ ./redstack build-image

#### Start up the reddwarf services in a screen session

    $ ./redstack start

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

    $ ./redstack install
    $ ./redstack kick-start

 or

    $ ./redstack install
    $ ./redstack build
    $ ./redstack initialize
    $ ./redstack build-image
    $ ./redstack start




