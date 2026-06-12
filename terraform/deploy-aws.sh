#!/usr/bin/env zsh
set -euo pipefail

# ════════════════════════════════════════════════════════════════════════════════
# TERRAFORM TWO-PHASE DEPLOYMENT SCRIPT
# ════════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}"
BOOTSTRAP_DIR="${SCRIPT_DIR}/bootstrap"

# ── Colours ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; PURPLE='\033[0;35m'; CYAN='\033[0;36m'; NC='\033[0m'

print_header()   { echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}\n${PURPLE} $1${NC}\n${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}"; }
print_step()     { echo -e "${BLUE}▶ $1${NC}"; }
print_success()  { echo -e "${GREEN}✅ $1${NC}"; }
print_warning()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()    { echo -e "${RED}❌ $1${NC}"; }

# ── Argument parsing ────────────────────────────────────────────────────────────
COMMAND=""         # bootstrap | migrate | status | cleanup | help (default)
TFVARS_FILE=""
TF_VARS=()         # Array to store -var arguments

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        bootstrap|migrate|status|cleanup|help)
            COMMAND="$1"
            shift
            ;;
        --tfvars)
            [[ -n "${2:-}" && "$2" != -* ]] || { print_error "--tfvars needs a filename"; exit 1; }
            TFVARS_FILE="$2"
            shift 2
            ;;
        -var)
            [[ -n "${2:-}" && "$2" != -* ]] || { print_error "-var needs a key=value argument"; exit 1; }
            TF_VARS+=("-var" "$2")
            shift 2
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

[[ -n "$COMMAND" ]] || COMMAND="help"

# ── Build terraform arguments ───────────────────────────────────────────────────
build_tf_args() {
    local args=()

    # Add tfvars file if specified
    [[ -n "$TFVARS_FILE" ]] && args+=("-var-file=$TFVARS_FILE")

    # Add individual -var arguments
    [[ ${#TF_VARS[@]} -gt 0 ]] && args+=("${TF_VARS[@]}")

    echo "${args[@]}"
}

# ── Variable file validation ────────────────────────────────────────────────────
check_tfvars() {
    if [[ -n "$TFVARS_FILE" ]]; then
        [[ -f "$TFVARS_FILE" ]] || { print_error "Specified tfvars file '$TFVARS_FILE' not found"; exit 1; }
        print_success "Using specified tfvars file: $TFVARS_FILE"
    else
        # Check for terraform.tfvars or *.auto.tfvars files
        # zsh null-glob qualifier (N): expands to nothing instead of erroring
        # with "no matches found" when no *.auto.tfvars file exists.
        local auto_tfvars=(*.auto.tfvars(N))
        if [[ -f "terraform.tfvars" ]]; then
            TFVARS_FILE="terraform.tfvars"
            print_success "Found terraform.tfvars"
        elif [[ ${#auto_tfvars[@]} -gt 0 ]]; then
            TFVARS_FILE="${auto_tfvars[1]}"
            print_success "Found auto tfvars file: $TFVARS_FILE"
        elif [[ ${#TF_VARS[@]} -eq 0 ]]; then
            # No explicit variables — Terraform falls back to the defaults in
            # variables.tf. Required variables without a default (or a TF_VAR_
            # env override) are still enforced by Terraform itself at plan time,
            # so we only warn here instead of failing pre-emptively. The
            # bootstrap phase in particular declares only defaulted variables.
            print_warning "No tfvars file or -var provided; using Terraform variable defaults / TF_VAR_ env."
        fi
    fi

    # Show variables being passed via -var.
    # Values of sensitive variables are redacted: echoing e.g. shared_secret
    # would leak it to the terminal and CI/session logs.
    if [[ ${#TF_VARS[@]} -gt 0 ]]; then
        print_success "Using command-line variables:"
        local kv key
        for kv in "${TF_VARS[@]}"; do
            [[ "$kv" == "-var" ]] && continue
            key="${kv%%=*}"
            case "$key" in
                *secret*|*password*|*token*|*credential*)
                    echo -e "${CYAN}  ${key}=***${NC}"
                    ;;
                *)
                    echo -e "${CYAN}  ${kv}${NC}"
                    ;;
            esac
        done
    fi
}

# ── Phase 1: bootstrap ──────────────────────────────────────────────────────────

# Read a variable value from the resolved tfvars file or -var overrides.
# Falls back to the default in variables.tf if not found.
read_tfvar() {
    local var_name="$1"
    local value=""
    local kv

    # Check -var overrides first (last one wins)
    for kv in "${TF_VARS[@]}"; do
        if [[ "$kv" == "${var_name}="* ]]; then
            value="${kv#*=}"
        fi
    done
    [[ -n "$value" ]] && { echo "$value"; return; }

    # Then check the tfvars file
    if [[ -n "$TFVARS_FILE" && -f "$TFVARS_FILE" ]]; then
        value=$(grep -E "^\s*${var_name}\s*=" "$TFVARS_FILE" | tail -1 | sed 's/.*= *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' | sed 's/\s*#.*//')
    fi
    [[ -n "$value" ]] && { echo "$value"; return; }

    # Fall back to default in variables.tf
    echo ""
}

# Generate backend.prod.hcl from tfvars state_*/region variables.
# This ensures backend config stays in sync with the tfvars single source of truth.
generate_backend_hcl() {
    local bucket region
    bucket=$(read_tfvar "state_bucket_name")
    region=$(read_tfvar "aws_region")

    [[ -n "$bucket" ]] || bucket="tiberio-tfstate"
    [[ -n "$region" ]] || region="eu-west-1"

    local hcl_file="$TERRAFORM_DIR/backend.prod.hcl"
    cat > "$hcl_file" <<EOF
# Auto-generated by deploy-aws.sh from tfvars state_*/region variables.
# Do not edit manually — update the tfvars file instead.

bucket       = "$bucket"
key          = "terraform.tfstate"
region       = "$region"
encrypt      = true
use_lockfile = true
EOF
    print_success "Generated $hcl_file"
}
run_bootstrap() {
    print_header "PHASE 1: TERRAFORM STATE STORAGE BOOTSTRAP"

    check_tfvars

    cd "$BOOTSTRAP_DIR"

    print_step "Checking AWS authentication"
    aws sts get-caller-identity > /dev/null 2>&1 || { print_error "Run 'aws configure' / 'aws sso login' first."; exit 1; }
    print_success "Authenticated to AWS account: $(aws sts get-caller-identity --query Account --output text)"

    print_step "Initializing Terraform (bootstrap)"
    terraform init
    terraform validate

    print_step "Planning bootstrap deployment"
    terraform plan $(build_tf_args) -out=bootstrap.tfplan

    print_step "Applying bootstrap configuration"
    terraform apply bootstrap.tfplan
    print_success "Bootstrap phase completed successfully!"

    print_step "Writing backend configuration"
    terraform output -json backend_configuration > backend_config.json
    jq -r 'to_entries[] | "  \(.key): \(.value)"' backend_config.json | while read -r line; do
        echo -e "${CYAN}${line}${NC}"
    done

    print_step "Generating backend.prod.hcl from tfvars"
    cd "$TERRAFORM_DIR"
    generate_backend_hcl

    print_warning "Next: run 'deploy-aws.sh migrate${TFVARS_FILE:+ --tfvars $TFVARS_FILE}'"
}

# ── Phase 2: migrate / main deploy ──────────────────────────────────────────────
run_migrate() {
    print_header "PHASE 2: MIGRATE TO REMOTE BACKEND & DEPLOY MAIN INFRASTRUCTURE"

    check_tfvars

    cd "$TERRAFORM_DIR"

    print_step "Generating backend.prod.hcl from tfvars"
    generate_backend_hcl

    local BACKEND_HCL="$TERRAFORM_DIR/backend.prod.hcl"

    print_step "Re-initializing Terraform with remote backend"
    rm -rf .terraform
    terraform init -backend-config="$BACKEND_HCL"
    print_success "Successfully migrated to remote backend!"

    terraform validate

    print_step "Planning main infrastructure"
    terraform plan $(build_tf_args) -out=main.tfplan

    print_warning "Ready to deploy main infrastructure. Continue? (y/N)"
    read -r response
    [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]] || { print_warning "Cancelled."; exit 0; }

    terraform apply main.tfplan
    print_success "Main infrastructure deployed successfully!"
    terraform output deployment_summary
}

# ── Utility functions (status / cleanup) ────────────────────────────────────────

# The main directory uses the remote backend once `terraform init
# -backend-config=backend.prod.hcl` has written an s3 backend block into
# .terraform/terraform.tfstate (see run_migrate).
uses_remote_backend() {
    [[ -f "$TERRAFORM_DIR/backend.prod.hcl" ]] \
        && grep -q '"type": *"s3"' "$TERRAFORM_DIR/.terraform/terraform.tfstate" 2>/dev/null
}

show_status() {
    print_header "TERRAFORM DEPLOYMENT STATUS"
    cd "$TERRAFORM_DIR"

    if uses_remote_backend; then
        print_success "✅ Using remote backend"
        terraform show > /dev/null 2>&1 && terraform output deployment_summary \
                                         || print_warning "Main infra not yet deployed"
    elif [[ -f "$BOOTSTRAP_DIR/terraform.tfstate" ]]; then
        print_success "✅ Bootstrap completed, ready for migration"
    else
        print_warning "⚠️  Bootstrap not run"
    fi
}

cleanup() {
    print_header "TERRAFORM CLEANUP"
    print_warning "Destroy **ALL** infrastructure? Type 'yes' to confirm:"
    read -r response; [[ "$response" == "yes" ]] || { print_warning "Cancelled."; exit 0; }

    cd "$TERRAFORM_DIR"
    terraform destroy -auto-approve
    rm -rf .terraform *.tfplan *.tfstate* backend_config.json backend.prod.hcl
    print_success "Cleanup completed"
}

# ── Dispatcher ──────────────────────────────────────────────────────────────────
case "$COMMAND" in
    bootstrap)
        run_bootstrap
        ;;
    migrate)
        run_migrate
        ;;
    status)
        show_status
        ;;
    cleanup)
        cleanup
        ;;
    help|*)
        print_header "TERRAFORM TWO-PHASE DEPLOYMENT"
        echo ""
        echo -e "${YELLOW}Usage: $0 {bootstrap|migrate|status|cleanup} [--tfvars <file>] [-var <key=value>]...${NC}"
        echo ""
        echo -e "${CYAN}Commands:${NC}"
        echo -e "  ${GREEN}bootstrap${NC}  - Run phase 1: Create state storage infrastructure"
        echo -e "  ${GREEN}migrate${NC}    - Run phase 2: Migrate to remote backend and deploy main infrastructure"
        echo -e "  ${GREEN}status${NC}     - Show current deployment status"
        echo -e "  ${GREEN}cleanup${NC}    - Destroy all infrastructure (⚠️  destructive)"
        echo -e "  ${GREEN}help${NC}       - Show this help message"
        echo ""
        echo -e "${CYAN}Options:${NC}"
        echo -e "  ${YELLOW}--tfvars <file>${NC}     - Use specified Terraform variables file"
        echo -e "  ${YELLOW}-var <key=value>${NC}     - Set a Terraform variable (can be used multiple times)"
        echo ""
        echo -e "${CYAN}Examples:${NC}"
        echo -e "  $0 bootstrap -var \"ami=abc123\" -var \"instance_type=t2.micro\""
        echo -e "  $0 migrate --tfvars prod.auto.tfvars -var \"environment=production\""
        echo ""
        echo -e "${YELLOW}Typical workflow:${NC}"
        echo -e "  1. $0 bootstrap    # Create state storage"
        echo -e "  2. $0 migrate      # Deploy main infrastructure"
        echo -e "  3. $0 status       # Check deployment status"
        echo ""
        ;;
esac
