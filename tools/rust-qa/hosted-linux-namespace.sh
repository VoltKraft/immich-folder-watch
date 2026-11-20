#!/usr/bin/env bash
# Provision only the sandbox launcher on this disposable Ubuntu Actions runner.
set -euo pipefail

[[ ${RUNNER_ENVIRONMENT:-} == github-hosted && ${RUNNER_OS:-} == Linux ]]
helper_dir=/opt/ifw-rust-qa-bwrap
profile="$helper_dir/ifw-rust-qa-bwrap.apparmor"
marker="${RUNNER_TEMP:?}/ifw-rust-qa-bwrap-provisioned"
probe=(--unshare-all --die-with-parent --new-session --ro-bind /usr /usr
       --symlink usr/lib /lib --symlink usr/lib64 /lib64 --proc /proc -- /usr/bin/id -u)

case ${1:-} in
  prepare)
    if current_uid=$(/usr/bin/bwrap "${probe[@]}") && [[ $current_uid == "$(id -u)" ]]; then
      echo "The packaged namespace launcher passed the isolated caller-UID check."
      exit 0
    fi
    [[ $(< /proc/sys/kernel/apparmor_restrict_unprivileged_userns) == 1 ]]
    # The system bwrap and its policy are left to the distribution. Only this
    # root-owned copy receives the userns permission for the lifetime of the job.
    sudo mkdir -- "$helper_dir"
    sudo chgrp "$(id -g)" "$helper_dir"
    sudo chmod 0750 "$helper_dir"
    touch "$marker"
    sudo install -o root -g "$(id -g)" -m 0750 /usr/bin/bwrap "$helper_dir/bwrap"
    sudo install -o root -g root -m 0644 "$(dirname "$0")/hosted-linux-namespace.apparmor" "$profile"
    sudo apparmor_parser --add "$profile"
    touch "$marker.loaded"
    observed_uid=$("$helper_dir/bwrap" "${probe[@]}")
    [[ $observed_uid == "$(id -u)" && $observed_uid != 0 ]]
    echo "$helper_dir" >> "${GITHUB_PATH:?}"
    echo "Verified the job-specific namespace launcher as UID $observed_uid."
    ;;
  cleanup)
    if [[ -f $marker ]]; then
      if [[ -f $marker.loaded ]]; then
        sudo apparmor_parser --remove "$profile"
      fi
      sudo rm -f -- "$helper_dir/bwrap" "$profile"
      sudo rmdir -- "$helper_dir"
      rm -f -- "$marker" "$marker.loaded"
    fi
    ;;
  *) exit 2 ;;
esac
