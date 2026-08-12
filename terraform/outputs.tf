output "beget_transit_status" {
  description = "Статус транзитного шлюза Beget"
  value = {
    ip                = var.beget_ip
    tcp_web_port      = 443
    udp_hopping_range = var.port_hopping_range
    mss_clamping      = "${var.tcp_mss_clamp} bytes"
  }
}

output "dataforest_master_status" {
  description = "Статус мастер-ноды Dataforest"
  value = {
    ip               = var.dataforest_ip
    hysteria_port    = var.hysteria_listen_port
    bandwidth_limit  = "${var.hysteria_bandwidth_limit_mbps} Mbps (Anti-DDoS Safe)"
    certificate_path = "/etc/letsencrypt/live/${var.vpn_domain}/"
  }
}

output "client_connection_sample" {
  description = "Пример строки подключения Hysteria 2 для клиента"
  value       = "hy2://${var.vpn_domain}:${var.hysteria_listen_port}/?mport=${replace(var.port_hopping_range, ":", "-")}&insecure=0#Void-Gaming-DE"
}
