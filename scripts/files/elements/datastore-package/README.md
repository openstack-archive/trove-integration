DIB element to copy datastore packages/installers to copy in the image

This element reads the environment variable DATASTORE_PKG_LOCATION and
depending on the type of source it copies the packages into the
/opt/datastore_package directory

If the DATASTORE_PKG_LOCATION is a file:
  # it will simply copy that file into the ${TMP_HOOKS_PATH}/datastore_package
    directory
  # then once inside the image it copies that package file to
    /opt/datastore_package directory


If the DATASTORE_PKG_LOCATION is a directory:
  # first it compreses that directory to a file,
  # then copy compressed tar to ${TMP_HOOKS_PATH}/datastore_package,
  # then once inside the image it extracts that tar into
    /opt/datastore_package directory


If the DATASTORE_PKG_LOCATION is a URL,
  # first it download the package from that URL
  # copies downloaded package file to ${TMP_HOOKS_PATH}/datastore_package
  # then once inside the image it copies that download package file to
    /opt/datastore_package directory

