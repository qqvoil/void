variable "beget_ip" {
  description = "IP-адрес транзитного сервера Beget (РФ)"
  type        = string
  default     = "185.23.34.168"
}

variable "dataforest_ip" {
  description = "IP-адрес мастер-сервера Dataforest (Германия)"
  type        = string
  default     = "91.238.123.4"
}

variable "ssh_user" {
  description = "SSH пользователь для управления серверами"
  type        = string
  default     = "root"
}

variable "ssh_private_key_path" {
  description = "Путь к приватному SSH-ключу"
  type        = string
  default     = "~/.ssh/id_rsa"
}

variable "hysteria_listen_port" {
  description = "Локальный порт, который слушает демон Hysteria 2"
  type        = number
  default     = 4433
}

variable "port_hopping_range" {
  description = "Диапазон портов для Port Hopping"
  type        = string
  default     = "40000:50000"
}

variable "hysteria_bandwidth_limit_mbps" {
  description = "Шейпинг скорости Hysteria (защита от Anti-DDoS Beget)"
  type        = number
  default     = 15
}

variable "tcp_mss_clamp" {
  description = "Размер TCP MSS Clamping для устранения MTU-фрагментации"
  type        = number
  default     = 1360
}

variable "vpn_domain" {
  description = "Основной домен VPN-сервиса"
  type        = string
  default     = "vpn.jointhevoid.ru"
}
