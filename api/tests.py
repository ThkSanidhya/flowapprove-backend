"""
Regression tests for multi-tenant isolation and approval authorization.

These cover the IDOR class of bugs patched in the
'fix: critical multi-tenant and security hardening' commit:

    * approve_document / reject_document / send_back_document
      must not allow cross-organization access.
    * Workflow step user assignment must stay within the
      requesting user's organization.
    * Document upload must reject cross-org workflowId.
"""

from io import BytesIO

from rest_framework.test import APITestCase, APIClient

from api.models import (
    Organization,
    User,
    Workflow,
    WorkflowStep,
    Document,
    DocumentApproval,
    DocumentVersion,
    DocumentHistory,
)


def _make_multi_step_doc(org, users, *, sendback_type="PREVIOUS_ONLY", current_step=1):
    """Create a workflow with len(users) sequential steps + matching Document + approvals."""
    wf = Workflow.objects.create(
        name=f"WF{len(users)}", organization=org, sendback_type=sendback_type
    )
    for i, u in enumerate(users, start=1):
        WorkflowStep.objects.create(workflow=wf, order=i, user=u)
    doc = Document.objects.create(
        title="doc", description="", file="documents/x.pdf",
        file_name="x.pdf", file_url="/media/documents/x.pdf",
        file_type="application/pdf", file_size=1,
        organization=org, workflow=wf, created_by=users[0],
        status="PENDING", current_step=current_step,
    )
    for i, u in enumerate(users, start=1):
        # Steps before current_step are APPROVED, the current step is PENDING, rest PENDING.
        st = "APPROVED" if i < current_step else "PENDING"
        DocumentApproval.objects.create(
            document=doc, step_order=i, user=u, status=st
        )
    return wf, doc


def _make_user(email, org, role="USER"):
    return User.objects.create_user(
        username=email,
        email=email,
        password="testpass123",
        name=email.split("@")[0],
        role=role,
        organization=org,
    )


def _make_workflow_with_document(org, approver, *, status="PENDING", current_step=1):
    wf = Workflow.objects.create(name="Test WF", organization=org)
    WorkflowStep.objects.create(workflow=wf, order=1, user=approver)
    doc = Document.objects.create(
        title="Secret",
        description="",
        file="documents/fake.pdf",
        file_name="fake.pdf",
        file_url="/media/documents/fake.pdf",
        file_type="application/pdf",
        file_size=10,
        organization=org,
        workflow=wf,
        created_by=approver,
        status=status,
        current_step=current_step,
    )
    DocumentApproval.objects.create(
        document=doc, step_order=1, user=approver, status="PENDING"
    )
    return wf, doc


class MultiTenantIsolationTests(APITestCase):
    """A user in Org B must never be able to touch Org A's documents."""

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org A")
        cls.org_b = Organization.objects.create(name="Org B")

        cls.alice = _make_user("alice@a.test", cls.org_a, role="ADMIN")
        cls.bob = _make_user("bob@b.test", cls.org_b, role="ADMIN")

        cls.wf_a, cls.doc_a = _make_workflow_with_document(cls.org_a, cls.alice)

    def setUp(self):
        self.client = APIClient()

    # ---- document detail ----

    def test_cross_org_document_detail_returns_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.get(f"/api/documents/{self.doc_a.id}")
        self.assertEqual(resp.status_code, 404)

    def test_own_org_document_detail_ok(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f"/api/documents/{self.doc_a.id}")
        self.assertEqual(resp.status_code, 200)

    # ---- approve ----

    def test_cross_org_approve_returns_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.post(
            f"/api/documents/{self.doc_a.id}/approve",
            {"comment": "pwn"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        # Document state must not have changed
        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.status, "PENDING")
        self.assertEqual(self.doc_a.current_step, 1)

    def test_approve_by_non_current_step_assignee_is_forbidden(self):
        carol = _make_user("carol@a.test", self.org_a)
        self.client.force_authenticate(carol)
        resp = self.client.post(
            f"/api/documents/{self.doc_a.id}/approve",
            {"comment": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_approve_by_current_step_assignee_advances(self):
        # Two-step workflow so the first approve advances instead of finalizing
        wf = Workflow.objects.create(name="WF2", organization=self.org_a)
        carol = _make_user("carol2@a.test", self.org_a)
        WorkflowStep.objects.create(workflow=wf, order=1, user=self.alice)
        WorkflowStep.objects.create(workflow=wf, order=2, user=carol)
        doc = Document.objects.create(
            title="t", description="", file="documents/x.pdf",
            file_name="x.pdf", file_url="/media/documents/x.pdf",
            file_type="application/pdf", file_size=1,
            organization=self.org_a, workflow=wf, created_by=self.alice,
            status="PENDING", current_step=1,
        )
        DocumentApproval.objects.create(document=doc, step_order=1, user=self.alice, status="PENDING")
        DocumentApproval.objects.create(document=doc, step_order=2, user=carol, status="PENDING")

        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            f"/api/documents/{doc.id}/approve", {"comment": "ok"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.current_step, 2)
        self.assertEqual(doc.status, "PENDING")

    # ---- reject ----

    def test_cross_org_reject_returns_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.post(
            f"/api/documents/{self.doc_a.id}/reject",
            {"comment": "pwn"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.status, "PENDING")

    def test_reject_by_non_assignee_forbidden(self):
        carol = _make_user("carol3@a.test", self.org_a)
        self.client.force_authenticate(carol)
        resp = self.client.post(
            f"/api/documents/{self.doc_a.id}/reject",
            {"comment": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.status, "PENDING")

    # ---- sendback ----

    def test_cross_org_sendback_returns_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.post(
            f"/api/documents/{self.doc_a.id}/sendback",
            {"reason": "pwn"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)


class WorkflowStepAssignmentTests(APITestCase):
    """Workflow steps cannot be assigned to users outside the caller's org."""

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org A")
        cls.org_b = Organization.objects.create(name="Org B")
        cls.alice = _make_user("alice2@a.test", cls.org_a, role="ADMIN")
        cls.mallory = _make_user("mallory@b.test", cls.org_b)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def test_create_workflow_with_cross_org_user_rejected(self):
        resp = self.client.post(
            "/api/workflows",
            {"name": "evil", "steps": [{"userId": self.mallory.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Workflow.objects.filter(name="evil").exists())

    def test_create_workflow_with_same_org_user_ok(self):
        carol = _make_user("carol4@a.test", self.org_a)
        resp = self.client.post(
            "/api/workflows",
            {"name": "ok", "steps": [{"userId": carol.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)


class UploadWorkflowScopingTests(APITestCase):
    """Document upload cannot reference a workflow from another org."""

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org A")
        cls.org_b = Organization.objects.create(name="Org B")
        cls.alice = _make_user("alice3@a.test", cls.org_a, role="ADMIN")
        cls.bob = _make_user("bob3@b.test", cls.org_b, role="ADMIN")
        cls.wf_b = Workflow.objects.create(name="B only", organization=cls.org_b)
        WorkflowStep.objects.create(workflow=cls.wf_b, order=1, user=cls.bob)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def _pdf(self, size=64):
        buf = BytesIO(b"%PDF-1.4\n" + b"x" * size)
        buf.name = "x.pdf"
        return buf

    def test_upload_cross_org_workflow_rejected(self):
        resp = self.client.post(
            "/api/documents/upload",
            {
                "file": self._pdf(),
                "title": "x",
                "description": "",
                "workflowId": self.wf_b.id,
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Document.objects.filter(title="x").exists())

    def test_upload_rejects_oversized_file(self):
        big = BytesIO(b"%PDF-1.4\n" + b"a" * (51 * 1024 * 1024))
        big.name = "big.pdf"
        resp = self.client.post(
            "/api/documents/upload",
            {"file": big, "title": "big", "description": ""},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 413)

    def test_upload_rejects_bad_mime(self):
        exe = BytesIO(b"MZ\x90\x00")
        exe.name = "evil.exe"
        resp = self.client.post(
            "/api/documents/upload",
            {"file": exe, "title": "evil", "description": ""},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)


# ----------------------------------------------------------------------
# Recall / withdraw
# ----------------------------------------------------------------------


class RecallDocumentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org A")
        cls.org_b = Organization.objects.create(name="Org B")
        cls.creator = _make_user("creator@a.test", cls.org_a, role="ADMIN")
        cls.other = _make_user("other@a.test", cls.org_a)
        cls.bob = _make_user("bob@b.test", cls.org_b, role="ADMIN")

    def setUp(self):
        self.client = APIClient()
        self.wf, self.doc = _make_multi_step_doc(self.org_a, [self.other])
        # the creator field on the helper-built doc is users[0]; override for clarity
        self.doc.created_by = self.creator
        self.doc.save()

    def test_creator_can_recall_pending_document(self):
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{self.doc.id}/recall",
            {"reason": "oops"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "CANCELLED")
        self.assertTrue(
            DocumentHistory.objects.filter(document=self.doc, action="RECALLED").exists()
        )

    def test_non_creator_cannot_recall(self):
        self.client.force_authenticate(self.other)
        resp = self.client.post(
            f"/api/documents/{self.doc.id}/recall", {"reason": "r"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "PENDING")

    def test_cannot_recall_approved_document(self):
        self.doc.status = "APPROVED"
        self.doc.save()
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{self.doc.id}/recall", {"reason": "r"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_recall_rejected_document(self):
        self.doc.status = "REJECTED"
        self.doc.save()
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{self.doc.id}/recall", {"reason": "r"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_cross_org_recall_returns_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.post(
            f"/api/documents/{self.doc.id}/recall", {"reason": "r"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)


# ----------------------------------------------------------------------
# Send back to any previous step
# ----------------------------------------------------------------------


class SendBackToAnyStepTests(APITestCase):
    """Partial reset, configurable targets."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org SB")
        cls.u1 = _make_user("s1@x.test", cls.org)
        cls.u2 = _make_user("s2@x.test", cls.org)
        cls.u3 = _make_user("s3@x.test", cls.org)

    def setUp(self):
        self.client = APIClient()

    def _doc(self, sendback_type="ANY_PREVIOUS", current_step=3):
        _, doc = _make_multi_step_doc(
            self.org, [self.u1, self.u2, self.u3],
            sendback_type=sendback_type, current_step=current_step,
        )
        return doc

    def test_sendback_any_previous_to_step_1_from_step_3(self):
        doc = self._doc(sendback_type="ANY_PREVIOUS", current_step=3)
        self.client.force_authenticate(self.u3)
        resp = self.client.post(
            f"/api/documents/{doc.id}/sendback",
            {"reason": "redo", "target_step": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.current_step, 1)
        self.assertEqual(doc.status, "PENDING")
        # Step 1 and step 2 approvals are reset to PENDING, step 3 is REJECTED
        statuses = {a.step_order: a.status for a in doc.approvals.all()}
        self.assertEqual(statuses[1], "PENDING")
        self.assertEqual(statuses[2], "PENDING")
        self.assertEqual(statuses[3], "REJECTED")

    def test_sendback_partial_reset_preserves_earlier_approved_steps(self):
        # current_step = 3 means steps 1 and 2 are APPROVED in the helper setup.
        doc = self._doc(sendback_type="ANY_PREVIOUS", current_step=3)
        self.client.force_authenticate(self.u3)
        resp = self.client.post(
            f"/api/documents/{doc.id}/sendback",
            {"reason": "fix", "target_step": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        statuses = {a.step_order: a.status for a in doc.approvals.all()}
        # Step 1 stays APPROVED, step 2 resets to PENDING, step 3 is REJECTED
        self.assertEqual(statuses[1], "APPROVED")
        self.assertEqual(statuses[2], "PENDING")
        self.assertEqual(statuses[3], "REJECTED")
        doc.refresh_from_db()
        self.assertEqual(doc.current_step, 2)

    def test_sendback_previous_only_rejects_skip(self):
        doc = self._doc(sendback_type="PREVIOUS_ONLY", current_step=3)
        self.client.force_authenticate(self.u3)
        resp = self.client.post(
            f"/api/documents/{doc.id}/sendback",
            {"reason": "r", "target_step": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        doc.refresh_from_db()
        self.assertEqual(doc.current_step, 3)

    def test_sendback_default_target_is_previous_step(self):
        doc = self._doc(sendback_type="PREVIOUS_ONLY", current_step=3)
        self.client.force_authenticate(self.u3)
        resp = self.client.post(
            f"/api/documents/{doc.id}/sendback",
            {"reason": "r"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.current_step, 2)

    def test_sendback_target_step_must_be_before_current(self):
        doc = self._doc(sendback_type="ANY_PREVIOUS", current_step=3)
        self.client.force_authenticate(self.u3)
        resp = self.client.post(
            f"/api/documents/{doc.id}/sendback",
            {"reason": "r", "target_step": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


# ----------------------------------------------------------------------
# Version upload
# ----------------------------------------------------------------------


class UploadVersionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org V")
        cls.creator = _make_user("creator@v.test", cls.org, role="ADMIN")
        cls.step2 = _make_user("s2@v.test", cls.org)
        cls.other = _make_user("other@v.test", cls.org)

    def setUp(self):
        self.client = APIClient()

    def _pdf(self, size=64):
        buf = BytesIO(b"%PDF-1.4\n" + b"x" * size)
        buf.name = "new.pdf"
        return buf

    def _doc(self, *, status="REJECTED", current_step=1):
        _, doc = _make_multi_step_doc(
            self.org, [self.creator, self.step2], current_step=current_step
        )
        doc.created_by = self.creator
        doc.status = status
        doc.save()
        return doc

    def test_creator_can_upload_version_after_rejection(self):
        doc = self._doc(status="REJECTED", current_step=1)
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf(), "version_note": "fixed typo"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "PENDING")
        self.assertEqual(doc.current_step, 1)
        # A version row was archived for the old file
        self.assertEqual(doc.versions.count(), 1)
        archived = doc.versions.first()
        self.assertEqual(archived.version_number, 1)
        # All approvals reset to PENDING
        for a in doc.approvals.all():
            self.assertEqual(a.status, "PENDING")

    def test_non_creator_cannot_upload_after_rejection(self):
        doc = self._doc(status="REJECTED", current_step=1)
        self.client.force_authenticate(self.other)
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)
        doc.refresh_from_db()
        self.assertEqual(doc.versions.count(), 0)

    def test_current_step_user_can_upload_after_sendback(self):
        # Simulate sendback: status PENDING, current_step=1 (user = creator)
        doc = self._doc(status="PENDING", current_step=1)
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        doc.refresh_from_db()
        # Partial reset — current_step did NOT change
        self.assertEqual(doc.current_step, 1)
        self.assertEqual(doc.status, "PENDING")

    def test_wrong_user_cannot_upload_after_sendback(self):
        doc = self._doc(status="PENDING", current_step=2)
        # current_step=2 means step2 is the assignee, not creator
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cannot_upload_version_for_approved_document(self):
        doc = self._doc(status="APPROVED", current_step=2)
        self.client.force_authenticate(self.creator)
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_version_rejects_oversized(self):
        doc = self._doc(status="REJECTED", current_step=1)
        self.client.force_authenticate(self.creator)
        big = BytesIO(b"%PDF-1.4\n" + b"a" * (51 * 1024 * 1024))
        big.name = "big.pdf"
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": big},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 413)

    def test_upload_version_rejects_bad_mime(self):
        doc = self._doc(status="REJECTED", current_step=1)
        self.client.force_authenticate(self.creator)
        exe = BytesIO(b"MZ\x90\x00")
        exe.name = "evil.exe"
        resp = self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": exe},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

    def test_version_archived_correctly(self):
        doc = self._doc(status="REJECTED", current_step=1)
        original_file_name = doc.file_name
        self.client.force_authenticate(self.creator)
        self.client.post(
            f"/api/documents/{doc.id}/upload-version",
            {"file": self._pdf()},
            format="multipart",
        )
        archived = DocumentVersion.objects.get(document=doc)
        self.assertEqual(archived.file_name, original_file_name)
        self.assertEqual(archived.file_type, "application/pdf")
