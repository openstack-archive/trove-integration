from proboscis import test
from proboscis.asserts import *
from nova.volume.manager import VolumeManager

# Look at nova/volume/manager.py
# get_driver
@test(groups=['nova.volumes'])
def hello_whitebox():
    manager = VolumeManager()
    driver = manager.get_driver()
    stats = driver.get_volume_stats(refresh=False)
    print(stats)
