variable "inventory_file" {
  type    = string
}

source "arm" "tezos_signer" {
  file_checksum_type    = "sha256"
  file_checksum_url     = "https://cdimage.ubuntu.com/releases/22.04.2/release/SHA256SUMS"
  file_target_extension = "xz"
  file_unarchive_cmd    = ["xz", "--decompress", "$ARCHIVE_PATH"]
  file_urls             = ["https://cdimage.ubuntu.com/releases/22.04.2/release/ubuntu-22.04.2-preinstalled-server-arm64+raspi.img.xz"]
  image_build_method    = "reuse"
  image_chroot_env      = ["PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"]
  image_mount_path      = "/tmp/tezos_signer_chroot"
  image_partitions {
    filesystem   = "fat"
    mountpoint   = "/boot/firmware"
    name         = "boot"
    size         = "256M"
    start_sector = "2048"
    type         = "c"
  }
  image_partitions {
    filesystem   = "ext4"
    mountpoint   = "/"
    name         = "root"
    size         = "2.8G"
    start_sector = "526336"
    type         = "83"
  }
  image_path                   = "${var.inventory_file}-rpi-sd-card.img"
  image_size                   = "3.1G"
  image_type                   = "dos"
  qemu_binary_destination_path = "/usr/bin/qemu-aarch64-static"
  qemu_binary_source_path      = "/usr/bin/qemu-aarch64-static"
}

build {
  sources = ["source.arm.tezos_signer"]

  provisioner "shell" {
    inline = ["mv /etc/resolv.conf /etc/resolv.conf.bk", "echo 'nameserver 8.8.8.8' > /etc/resolv.conf"]
  }
  provisioner "ansible" {
    inventory_file_template = "tezos-remote-signer ansible_host=/tmp/tezos_signer_chroot ansible_connection=chroot\n"
    playbook_file           = "./tezos-remote-signer-bootstrap.yaml"
    user                    = "root"
  }

  provisioner "ansible" {
    inventory_file = var.inventory_file
    playbook_file  = "./tezos-remote-signer.yaml"
    user           = "tezos"
  }

}
