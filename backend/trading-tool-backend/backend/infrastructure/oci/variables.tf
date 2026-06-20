variable "tenancy_ocid" {
  type = string
}

variable "compartment_ocid" {
  type = string
}

variable "user_ocid" {
  type = string
}

variable "fingerprint" {
  type = string
}

variable "private_key_path" {
  type = string
}

variable "region" {
  type    = string
  default = "eu-frankfurt-1"
}

variable "vcn_cidr_block" {
  type    = string
  default = "10.40.0.0/16"
}

variable "availability_domain_index" {
  type    = number
  default = 0
}

variable "instance_shape" {
  type    = string
  default = "VM.Standard.E2.1.Micro"
}

variable "instance_ocpus" {
  type    = number
  default = 1
}

variable "instance_memory_gbs" {
  type    = number
  default = 1
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_rsa.pub"
}
