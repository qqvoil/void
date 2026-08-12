# Модуль 1: Развертывание и тюнинг транзитного шлюза (Beget)
module "beget_transit" {
  source = "./modules/beget_transit"

  beget_ip             = var.beget_ip
  dataforest_ip        = var.dataforest_ip
  ssh_user             = var.ssh_user
  ssh_private_key_path = var.ssh_private_key_path

  port_hopping_range = var.port_hopping_range
  tcp_mss_clamp      = var.tcp_mss_clamp
  vpn_domain         = var.vpn_domain
}

# Модуль 2: Развертывание мастер-ноды и Hysteria 2 (Dataforest)
module "dataforest_master" {
  source = "./modules/dataforest_master"

  dataforest_ip        = var.dataforest_ip
  ssh_user             = var.ssh_user
  ssh_private_key_path = var.ssh_private_key_path

  hysteria_listen_port          = var.hysteria_listen_port
  port_hopping_range            = var.port_hopping_range
  hysteria_bandwidth_limit_mbps = var.hysteria_bandwidth_limit_mbps
  vpn_domain                    = var.vpn_domain

  depends_on = [module.beget_transit]
}
