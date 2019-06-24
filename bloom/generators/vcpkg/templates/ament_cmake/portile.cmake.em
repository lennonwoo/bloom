@[if git_source == 'gitlab']@
vcpkg_from_gitlab
@[elif git_source == 'github']@
vcpkg_from_github
@[elif git_source == 'bitbucket']@
vcpkg_from_bitbucket
@[end if](
    OUT_SOURCE_PATH SOURCE_PATH
    REPO @(user_name)/@(repo_name)
    REF @(tag_name)
    HEAD_REF master
)

vcpkg_configure_cmake(
    SOURCE_PATH ${SOURCE_PATH}
)

