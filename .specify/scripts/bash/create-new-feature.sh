#!/bin/bash

# create-new-feature.sh
# Creates a new feature branch and initializes spec file

set -e

# Parse arguments
SHORT_NAME=""
FEATURE_DESC=""
TIMESTAMP=false
NUMBER=""
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --short-name)
            SHORT_NAME="$2"
            shift 2
            ;;
        --timestamp)
            TIMESTAMP=true
            shift
            ;;
        --number)
            NUMBER="$2"
            shift 2
            ;;
        --json|-Json)
            JSON_OUTPUT=true
            shift
            ;;
        *)
            # Remaining args are feature description
            if [ -z "$FEATURE_DESC" ]; then
                FEATURE_DESC="$1"
            fi
            shift
            ;;
    esac
done

# Validate inputs
if [ -z "$SHORT_NAME" ] || [ -z "$FEATURE_DESC" ]; then
    echo "Error: --short-name and feature description are required"
    echo "Usage: $0 [--short-name NAME] [--json] [--timestamp] [--number N] DESCRIPTION"
    exit 1
fi

# Get repo root
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Determine branch prefix
if [ "$TIMESTAMP" = true ]; then
    BRANCH_PREFIX=$(date +%Y%m%d-%H%M%S)
else
    # Get next sequential number
    CURRENT_NUM=0
    if [ -n "$NUMBER" ]; then
        CURRENT_NUM=$NUMBER
    else
        # Find highest existing number
        for branch in $(git branch --list --format='%(refname:short)' | grep -E '^[0-9]+-'); do
            NUM=$(echo "$branch" | cut -d'-' -f1)
            if [ "$NUM" -gt "$CURRENT_NUM" ] 2>/dev/null; then
                CURRENT_NUM=$NUM
            fi
        done
        CURRENT_NUM=$((CURRENT_NUM + 1))
    fi
    BRANCH_PREFIX=$(printf "%03d" $CURRENT_NUM)
fi

# Create branch name
BRANCH_NAME="${BRANCH_PREFIX}-${SHORT_NAME}"

# Check if branch already exists
if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    echo "Error: Branch '${BRANCH_NAME}' already exists"
    exit 1
fi

# Create feature directory
FEATURE_DIR="specs/${BRANCH_PREFIX}-${SHORT_NAME}"
mkdir -p "$FEATURE_DIR"

# Create spec file
SPEC_FILE="${FEATURE_DIR}/spec.md"

# Create spec template content
cat > "$SPEC_FILE" << EOF
# Feature Specification: [Feature Name]

**Feature Branch**: \`\`\`${BRANCH_NAME}\`\`\`  
**Created**: $(date +%Y-%m-%d)  
**Status**: Draft  
**Input**: ${FEATURE_DESC}

## Clarifications

### Session $(date +%Y-%m-%d)

TODO: Add clarification notes if needed

## User Scenarios & Testing

### User Story 1 - [Title] (Priority: P1)

TODO: Add user story

**Why this priority**: [Rationale]

**Independent Test**: [How to verify]

**Acceptance Scenarios**:

  1. TODO: Add acceptance scenario

---

## Requirements

### Functional Requirements

- **FR-001**: TODO: Add functional requirement

### Observability Requirements

- **OR-001**: TODO: Add observability requirement

### Key Entities

- **TODO**: TODO: Add key entity

## Success Criteria

### Measurable Outcomes

- **SC-001**: TODO: Add measurable outcome

### Validation Metrics

- TODO: Add validation metrics

## Assumptions

- TODO: Add assumptions
EOF

# Create branch and checkout
git checkout -b "$BRANCH_NAME"

# Create initial spec file
git add "$SPEC_FILE"
git commit -m "feat: add feature spec for ${FEATURE_DESC}"

# Output results
if [ "$JSON_OUTPUT" = true ]; then
    cat << EOF
{
  "branch_name": "${BRANCH_NAME}",
  "feature_dir": "${FEATURE_DIR}",
  "spec_file": "${SPEC_FILE}"
}
EOF
else
    echo "Feature branch created: ${BRANCH_NAME}"
    echo "Feature directory: ${FEATURE_DIR}"
    echo "Spec file: ${SPEC_FILE}"
fi
