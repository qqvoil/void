resource "null_resource" "provision_beget" {
  triggers = {
    sysctl_hash   = md5(templatefile("${path.module}/templates/sysctl.conf.tftpl", {}))
    iptables_hash = md5(templatefile("${path.module}/templates/iptables_rules.sh.tftpl", {
      dataforest_ip      = var.dataforest_ip
      port_hopping_range = var.port_hopping_range
      tcp_mss_clamp      = var.tcp_mss_clamp
    }))
  }

  connection {
    type        = "ssh"
    host        = var.beget_ip
    user        = var.ssh_user
    private_key = file(pathexpand(var.ssh_private_key_path))
    timeout     = "1m"
  }

  provisioner "remote-exec" {
    inline = [
      "DEBIAN_FRONTEND=noninteractive apt-get update -y",
      "DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent netfilter-persistent haproxy"
    ]
  }

  provisioner "file" {
    content     = templatefile("${path.module}/templates/sysctl.conf.tftpl", {})
    destination = "/etc/sysctl.d/99-vpn-transit.conf"
  }

  provisioner "file" {
    content = templatefile("${path.module}/templates/iptables_rules.sh.tftpl", {
      dataforest_ip      = var.dataforest_ip
      port_hopping_range = var.port_hopping_range
      tcp_mss_clamp      = var.tcp_mss_clamp
    })
    destination = "/usr/local/bin/apply-vpn-iptables.sh"
  }

  provisioner "remote-exec" {
    inline = [
      "sysctl --system",
      "chmod +x /usr/local/bin/apply-vpn-iptables.sh",
      "/usr/local/bin/apply-vpn-iptables.sh",
      "netfilter-persistent save"
    ]
  }
}
