variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "trusted_principal_arn" {
  type        = string
  description = "Exact IAM user/role ARN allowed to assume optimizer roles"
}
variable "external_id" {
  type      = string
  sensitive = true
}
variable "create_demo_instance" {
  type    = bool
  default = false
}
variable "ami_id" {
  type    = string
  default = ""
}
variable "vpc_id" {
  type    = string
  default = ""
}
variable "subnet_id" {
  type    = string
  default = ""
}
variable "instance_type" {
  type    = string
  default = "t3.micro"
}
