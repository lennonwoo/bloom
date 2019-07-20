include(vcpkg_common_functions)

set(VCPKG_BUILD_TYPE release)

@[if git_source == 'gitlab']@
vcpkg_from_gitlab(
@[elif git_source == 'github']@
vcpkg_from_github(
@[elif git_source == 'bitbucket']@
vcpkg_from_bitbucket(
@[end if]@
    OUT_SOURCE_PATH SOURCE_PATH
    REPO @(user_name)/@(repo_name)
    REF @(tag_name)
)

set(ROS_BASE_PATH "C:/opt/ros/@(ros_distro)")
file(TO_NATIVE_PATH "${ROS_BASE_PATH}" ROS_BASE_PATH)

vcpkg_configure_cmake(
    SOURCE_PATH ${SOURCE_PATH}
    OPTIONS
        -DCMAKE_INSTALL_PREFIX=${ROS_BASE_PATH}
        -DAMENT_PREFIX_PATH=${ROS_BASE_PATH}
)

vcpkg_install_cmake()
