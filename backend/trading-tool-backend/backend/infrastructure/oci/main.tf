terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

locals {
  environments = {
    production = {
      cidr_block       = "10.40.10.0/24"
      display_name     = "tradamind-production"
      frontend_port    = 5002
      backend_port     = 8000
      assign_public_ip = true
    }
    staging = {
      cidr_block       = "10.40.20.0/24"
      display_name     = "tradamind-staging"
      frontend_port    = 5102
      backend_port     = 8100
      assign_public_ip = true
    }
  }

  ingress_rules = flatten([
    for env_name, env in local.environments : [
      {
        environment = env_name
        description = "${env_name} ssh"
        port        = 22
      },
      {
        environment = env_name
        description = "${env_name} http"
        port        = 80
      },
      {
        environment = env_name
        description = "${env_name} https"
        port        = 443
      },
    ]
  ])
}

resource "oci_core_vcn" "trading_vcn" {
  cidr_block     = var.vcn_cidr_block
  compartment_id = var.compartment_ocid
  display_name   = "tradamind-vcn"
  dns_label      = "tradamind"
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.trading_vcn.id
  display_name   = "tradamind-igw"
  enabled        = true
}

resource "oci_core_route_table" "public_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.trading_vcn.id
  display_name   = "tradamind-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.igw.id
  }
}

resource "oci_core_subnet" "public_subnet" {
  for_each = local.environments

  cidr_block                 = each.value.cidr_block
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.trading_vcn.id
  display_name               = "${each.key}-public-subnet"
  dns_label                  = each.key == "production" ? "prodsubnet" : "stgsubnet"
  route_table_id             = oci_core_route_table.public_rt.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_network_security_group" "env_nsg" {
  for_each = local.environments

  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.trading_vcn.id
  display_name   = "${each.key}-nsg"
}

resource "oci_core_network_security_group_security_rule" "allow_ingress" {
  for_each = {
    for rule in local.ingress_rules :
    "${rule.environment}-${rule.port}" => rule
  }

  network_security_group_id = oci_core_network_security_group.env_nsg[each.value.environment].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = each.value.description

  tcp_options {
    destination_port_range {
      min = each.value.port
      max = each.value.port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "allow_egress_all" {
  for_each = local.environments

  network_security_group_id = oci_core_network_security_group.env_nsg[each.key].id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "${each.key} all egress"
}

resource "oci_core_instance" "environment_vm" {
  for_each = local.environments

  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_index].name
  compartment_id      = var.compartment_ocid
  shape               = var.instance_shape
  display_name        = each.value.display_name

  shape_config {
    memory_in_gbs = var.instance_memory_gbs
    ocpus         = var.instance_ocpus
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_image.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public_subnet[each.key].id
    assign_public_ip = each.value.assign_public_ip
    nsg_ids          = [oci_core_network_security_group.env_nsg[each.key].id]
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tpl", {
      environment   = each.key
      app_env       = each.key == "production" ? "production" : "staging"
      frontend_port = each.value.frontend_port
      backend_port  = each.value.backend_port
    }))
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

data "oci_core_images" "ubuntu_image" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}
