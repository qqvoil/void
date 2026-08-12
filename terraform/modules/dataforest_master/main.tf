resource "null_resource" "provision_dataforest" {
  triggers = {
    funnel_hash = md5(templatefile("${path.module}/templates/iptables_funnel.sh.tftpl", {
      port_hopping_range   = var.port_hopping_range
      hysteria_listen_port = var.hysteria_listen_port
    }))
    hysteria_hash = md5(templatefile("${path.module}/templates/hysteria_config.yaml.tftpl", {
      hysteria_listen_port          = var.hysteria_listen_port
      hysteria_bandwidth_limit_mbps = var.hysteria_bandwidth_limit_mbps
      vpn_domain                    = var.vpn_domain
    }))
  }

  connection {
    type        = "ssh"
    host        = var.dataforest_ip
    user        = var.ssh_user
    private_key = file(pathexpand(var.ssh_private_key_path))
    timeout     = "1m"
  }

  provisioner "remote-exec" {
    inline = [
      "DEBIAN_FRONTEND=noninteractive apt-get update -y",
      "DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent netfilter-persistent curl",
      "mkdir -p /etc/hysteria"
    ]
  }

  provisioner "file" {
    content = templatefile("${path.module}/templates/iptables_funnel.sh.tftpl", {
      port_hopping_range   = var.port_hopping_range
      hysteria_listen_port = var.hysteria_listen_port
    })
    destination = "/usr/local/bin/apply-dataforest-funnel.sh"
  }

  provisioner "file" {
    content = templatefile("${path.module}/templates/hysteria_config.yaml.tftpl", {
      hysteria_listen_port          = var.hysteria_listen_port
      hysteria_bandwidth_limit_mbps = var.hysteria_bandwidth_limit_mbps
      vpn_domain                    = var.vpn_domain
    })
    destination = "/etc/hysteria/config.yaml"
  }

  provisioner "remote-exec" {
    inline = [
      "chmod +x /usr/local/bin/apply-dataforest-funnel.sh",
      "/usr/local/bin/apply-dataforest-funnel.sh",
      "netfilter-persistent save"
    ]
  }
}
