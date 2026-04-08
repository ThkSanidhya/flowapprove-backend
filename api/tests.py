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
)


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
