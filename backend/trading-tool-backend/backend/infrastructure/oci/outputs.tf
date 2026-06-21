output "environment_public_ips" {
  value = {
    for env_name, instance in oci_core_instance.environment_vm :
    env_name => instance.public_ip
  }
}

output "environment_private_ips" {
  value = {
    for env_name, instance in oci_core_instance.environment_vm :
    env_name => instance.private_ip
  }
}

output "environment_names" {
  value = keys(oci_core_instance.environment_vm)
}
