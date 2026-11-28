#!/bin/bash
# Run only on the VM that received this read-only seed and its matching SMBIOS serial.
set -eu
test "$(cat /sys/class/dmi/id/product_name)" = IFW-Noble-Portal-QA
test "$(cat /sys/class/dmi/id/product_serial)" = "$(cat /mnt/ifw/trial-id)"
test "$(findmnt -no LABEL -T /mnt/ifw)" = cidata
mkdir -p /mnt/result
mount -L IFWRESULT /mnt/result
exec >/mnt/result/guest.log 2>&1
trap 'echo "$?" >/mnt/result/exit; sync' EXIT
cp /mnt/ifw/trial-id /mnt/result/trial-id
cp /proc/sys/kernel/random/boot_id /mnt/result/boot-id
dpkg --print-architecture >/mnt/result/arch
cp /var/lib/dpkg/status /mnt/result/dpkg-status
case "$(cat /mnt/ifw/stage)" in
    inventory) uname -a ;;
    package) bash /mnt/ifw/payload/package.sh ;;
    lease|lease-stock) bash /mnt/ifw/payload/lease.sh ;;
    *) exit 2 ;;
esac
