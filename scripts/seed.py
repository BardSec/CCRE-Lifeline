#!/usr/bin/env python3
"""
Seed script: creates a demo tenant, admin user, and example K12 cybersecurity rubric.

Run: docker compose exec web python scripts/seed.py
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on the path when running inside Docker
sys.path.insert(0, "/app")

from app.auth.security import hash_password
from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    Rubric, RubricDomain, RubricItem, Tenant, User, UserRole
)

settings = get_settings()


MATURITY_LABELS = {
    "1": "Initial — Ad-hoc, undocumented, reactive",
    "2": "Developing — Some documentation, inconsistently applied",
    "3": "Defined — Documented, consistently applied district-wide",
    "4": "Managed — Measured, reviewed, and improved regularly",
    "5": "Optimizing — Continuous improvement, benchmarked externally",
}

RUBRIC_DATA = {
    "name": "K12 Cybersecurity Framework",
    "version": "1.0",
    "description": (
        "A maturity model for K12 technology teams to assess cybersecurity posture "
        "across Identity & Access Management, Data Protection & Privacy, and "
        "Incident Response & Recovery domains."
    ),
    "domains": [
        {
            "name": "Identity & Access Management",
            "description": "Controls for managing digital identities, authentication, and authorization.",
            "sort_order": 1,
            "items": [
                {
                    "code": "IAM-1",
                    "title": "Multi-Factor Authentication",
                    "description": "MFA is enforced for all staff accounts accessing district systems.",
                    "guidance": (
                        "Verify MFA is enabled for email (M365/Google), SIS, finance, and VPN. "
                        "Check policies for exceptions and privileged accounts."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "screenshot", "audit_report"],
                    "sort_order": 1,
                },
                {
                    "code": "IAM-2",
                    "title": "Privileged Access Management",
                    "description": "Privileged accounts are inventoried, least-privilege principles applied, and PAM tooling used.",
                    "guidance": (
                        "Review list of domain admin, local admin, and service accounts. "
                        "Confirm Just-In-Time access or approval workflows exist."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "screenshot", "log"],
                    "sort_order": 2,
                },
                {
                    "code": "IAM-3",
                    "title": "User Lifecycle Management",
                    "description": "Onboarding and offboarding processes ensure timely provisioning and de-provisioning.",
                    "guidance": (
                        "Confirm HR feeds are automated to AD/Azure AD. "
                        "Review termination checklist and spot-check recently departed staff accounts."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "procedure", "log"],
                    "sort_order": 3,
                },
                {
                    "code": "IAM-4",
                    "title": "Single Sign-On (SSO)",
                    "description": "SSO is implemented for major district applications to reduce credential sprawl.",
                    "guidance": (
                        "Inventory applications and confirm SSO coverage. "
                        "Verify orphaned local accounts are removed when SSO is adopted."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["screenshot", "audit_report"],
                    "sort_order": 4,
                },
                {
                    "code": "IAM-5",
                    "title": "Access Review & Recertification",
                    "description": "Periodic access reviews are conducted to validate role appropriateness.",
                    "guidance": (
                        "Verify scheduled access review cadence (quarterly or annually). "
                        "Review records of completed reviews and remediation actions."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["audit_report", "log", "policy"],
                    "sort_order": 5,
                },
            ],
        },
        {
            "name": "Data Protection & Privacy",
            "description": "Controls for classifying, protecting, and governing sensitive student and staff data.",
            "sort_order": 2,
            "items": [
                {
                    "code": "DPP-1",
                    "title": "Data Classification Policy",
                    "description": "A formal data classification policy defines sensitivity tiers (public, internal, confidential, restricted).",
                    "guidance": (
                        "Review the written data classification policy. "
                        "Confirm staff training on classification levels and how to handle each tier."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "training_record"],
                    "sort_order": 1,
                },
                {
                    "code": "DPP-2",
                    "title": "Student Data Privacy (FERPA/COPPA)",
                    "description": "Processes ensure FERPA and COPPA compliance for third-party vendors and data sharing.",
                    "guidance": (
                        "Review vendor data processing agreements (DPAs). "
                        "Confirm a student data inventory exists and annual FERPA notice is published."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "contract", "audit_report"],
                    "sort_order": 2,
                },
                {
                    "code": "DPP-3",
                    "title": "Encryption at Rest & In Transit",
                    "description": "Sensitive data is encrypted at rest (AES-256) and in transit (TLS 1.2+).",
                    "guidance": (
                        "Verify disk encryption on endpoints (BitLocker/FileVault). "
                        "Check TLS configuration on public-facing services; confirm no deprecated protocols."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["screenshot", "audit_report", "log"],
                    "sort_order": 3,
                },
                {
                    "code": "DPP-4",
                    "title": "Data Loss Prevention (DLP)",
                    "description": "DLP controls are in place to detect and prevent unauthorized exfiltration of sensitive data.",
                    "guidance": (
                        "Review DLP policy configuration in M365/Google Workspace or dedicated DLP tool. "
                        "Check alert logs and incident response for DLP events."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["screenshot", "policy", "log"],
                    "sort_order": 4,
                },
                {
                    "code": "DPP-5",
                    "title": "Backup & Recovery",
                    "description": "Critical data is backed up on a defined schedule and recovery is tested regularly.",
                    "guidance": (
                        "Verify backup coverage and retention policy. "
                        "Confirm at least annual restore test with documented results."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "log", "audit_report"],
                    "sort_order": 5,
                },
            ],
        },
        {
            "name": "Incident Response & Recovery",
            "description": "Capabilities to detect, contain, eradicate, and recover from cybersecurity incidents.",
            "sort_order": 3,
            "items": [
                {
                    "code": "IRR-1",
                    "title": "Incident Response Plan",
                    "description": "A documented IRP defines roles, escalation paths, communication templates, and playbooks.",
                    "guidance": (
                        "Review the IRP document for completeness: scope, roles, playbooks, communication trees. "
                        "Confirm plan is reviewed at least annually and after significant incidents."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "procedure"],
                    "sort_order": 1,
                },
                {
                    "code": "IRR-2",
                    "title": "Security Monitoring & SIEM",
                    "description": "Log aggregation and alerting is in place; key events are monitored and triaged.",
                    "guidance": (
                        "Confirm log sources (endpoints, firewall, identity) feed into SIEM or MDR. "
                        "Review alert tuning and escalation procedures."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["screenshot", "audit_report", "log"],
                    "sort_order": 2,
                },
                {
                    "code": "IRR-3",
                    "title": "Tabletop Exercises",
                    "description": "Incident response tabletop exercises are conducted at least annually with key stakeholders.",
                    "guidance": (
                        "Review exercise documentation, attendance records, and after-action reports. "
                        "Confirm findings are tracked and remediated."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["audit_report", "training_record"],
                    "sort_order": 3,
                },
                {
                    "code": "IRR-4",
                    "title": "Ransomware Resilience",
                    "description": "Controls specifically address ransomware: segmentation, immutable backups, and recovery playbook.",
                    "guidance": (
                        "Verify network segmentation limits blast radius. "
                        "Confirm offline or immutable backup copies exist and recovery RTO/RPO are defined."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "screenshot", "log"],
                    "sort_order": 4,
                },
                {
                    "code": "IRR-5",
                    "title": "Breach Notification Process",
                    "description": "A defined process ensures timely breach notification to regulators, affected individuals, and stakeholders.",
                    "guidance": (
                        "Review notification procedure for FERPA, state breach law, and cyber insurance requirements. "
                        "Confirm legal counsel and PR contacts are embedded in the IRP."
                    ),
                    "maturity_levels": MATURITY_LABELS,
                    "evidence_types": ["policy", "procedure", "contract"],
                    "sort_order": 5,
                },
            ],
        },
    ],
}


def seed() -> None:
    db = SessionLocal()
    try:
        # Check if already seeded
        existing_rubric = db.query(Rubric).filter(
            Rubric.name == RUBRIC_DATA["name"]
        ).first()

        if not existing_rubric:
            print("Seeding rubric…")
            rubric = Rubric(
                name=RUBRIC_DATA["name"],
                version=RUBRIC_DATA["version"],
                description=RUBRIC_DATA["description"],
            )
            db.add(rubric)
            db.flush()

            for domain_data in RUBRIC_DATA["domains"]:
                domain = RubricDomain(
                    rubric_id=rubric.id,
                    name=domain_data["name"],
                    description=domain_data["description"],
                    sort_order=domain_data["sort_order"],
                )
                db.add(domain)
                db.flush()

                for item_data in domain_data["items"]:
                    item = RubricItem(
                        domain_id=domain.id,
                        code=item_data["code"],
                        title=item_data["title"],
                        description=item_data["description"],
                        guidance=item_data["guidance"],
                        maturity_levels=item_data["maturity_levels"],
                        evidence_types=item_data["evidence_types"],
                        sort_order=item_data["sort_order"],
                    )
                    db.add(item)
            print(f"  Rubric '{rubric.name}' created with 3 domains, 15 items.")
        else:
            print("Rubric already exists, skipping.")
            rubric = existing_rubric

        # Demo tenant
        existing_tenant = db.query(Tenant).filter(
            Tenant.name == settings.SEED_TENANT_NAME
        ).first()

        if not existing_tenant:
            print(f"Seeding tenant '{settings.SEED_TENANT_NAME}'…")
            tenant = Tenant(name=settings.SEED_TENANT_NAME)
            db.add(tenant)
            db.flush()
        else:
            print(f"Tenant '{settings.SEED_TENANT_NAME}' already exists, skipping.")
            tenant = existing_tenant

        # Admin user
        existing_admin = db.query(User).filter(
            User.tenant_id == tenant.id,
            User.email == settings.SEED_ADMIN_EMAIL,
        ).first()

        if not existing_admin:
            print(f"Seeding admin user '{settings.SEED_ADMIN_EMAIL}'…")
            admin = User(
                tenant_id=tenant.id,
                email=settings.SEED_ADMIN_EMAIL,
                password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                name="District Admin",
                role=UserRole.admin,
                is_active=True,
            )
            db.add(admin)
        else:
            print(f"Admin user '{settings.SEED_ADMIN_EMAIL}' already exists, skipping.")

        db.commit()
        print("\n✓ Seed complete.")
        print(f"  Login: {settings.SEED_ADMIN_EMAIL}")
        print(f"  Password: {settings.SEED_ADMIN_PASSWORD}")
        print(f"  Tenant: {settings.SEED_TENANT_NAME}")

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
