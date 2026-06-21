# OCI Environment Provisioning

This Terraform stack provisions two separate Oracle environments:

- `production`
- `staging`

Each environment gets:

- its own public subnet
- its own network security group
- its own Ubuntu compute instance
- its own local service ports for frontend/backend

Default ports:

- production frontend/backend: `5002` / `8000`
- staging frontend/backend: `5102` / `8100`

## Usage

1. Copy `terraform.tfvars.example` to `terraform.tfvars`
2. Fill in your OCI tenancy/user/compartment values
3. Run:

```bash
terraform init
terraform plan
terraform apply
```

## Important Notes

- This stack does **not** create DNS records for `app.tradamind.com`, `api.tradamind.com`, `staging.tradamind.com`, or `api-staging.tradamind.com`. Add those after instance public IPs are known.
- This stack assumes Postgres and Redis run locally on each instance for environment separation.
- Secrets, `.env` files, and SSL certificates remain operational steps after provisioning.
