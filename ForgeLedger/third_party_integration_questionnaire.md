# ForgeLedger Integration: Discovery & Requirements Questionnaire

To successfully integrate your application with ForgeLedger (our Governance-Native Evidence Infrastructure), we need to map your agentic workflows to our structured governance event model. 

ForgeLedger acts as a tamper-evident, policy-aware evidence substrate. It does not replace your application's logic; rather, it securely records *why* decisions were made, *what* boundaries were crossed, and *who/what* authorized them.

Please provide details on the following areas so we can prepare a tailored integration plan.

---

## 1. Agent Workflow & Use Case
*Understanding the operational boundary and risk profile of your AI agents.*

- **Primary Workflows:** What are the core tasks your AI agents perform? (e.g., retrieving data, updating CRM records, generating technical plans)
- **Agent Autonomy:** Are these agents purely advisory (drafting content for a human to review), or do they take autonomous actions (calling external APIs, modifying state)?
- **Blast Radius:** What is the worst-case scenario if the agent hallucinates or makes a bad decision?

## 2. Event Emission & Interception Points
*Identifying where we need to hook into your application to emit ForgeLedger events.*

Does your application currently have centralized interception points (middleware, decorators, or event buses) for the following actions?
- **Admission / Authentication:** When a user or system invokes an agent.
- **Policy Evaluation:** When checking if an agent is authorized to perform a specific action or access specific data.
- **Model Inferences (LLM Calls):** When sending prompts to and receiving responses from external model providers (e.g., OpenAI, Anthropic, local models).
- **Tool / API Execution:** When the agent executes a tool or external API.
- **Human-in-the-Loop (HITL):** When an action is escalated to a human for approval or review.

## 3. Data Sensitivity & Redaction
*Ensuring sensitive data is minimized and redacted before entering the evidence ledger.*

- **Data Classes:** What types of sensitive data does your application handle? (e.g., PII, PHI/Health Data, Financial Credentials, Proprietary Source Code)
- **Redaction Capabilities:** Does your application already identify and classify sensitive fields in payloads, or will we need to implement ingest-time redaction rules via ForgeLedger?

## 4. Tenant Context & Isolation
*Understanding the data residency and isolation boundaries.*

- **Multi-Tenancy:** Is your application single-tenant or multi-tenant? 
- **Residency Requirements:** Are there specific data residency or geographic isolation requirements for the evidence logs?

## 5. Security & Key Management
*ForgeLedger uses HMAC-SHA256 to authenticate events and hash-chains for integrity.*

- **Secret Management:** How does your application currently manage secrets and keys? (e.g., AWS KMS, Azure Key Vault, HashiCorp Vault, environment variables)
- **Identity & RBAC:** How do you track the "actor" (both human users and agent IDs) across a distributed workflow?

## 6. Compliance & Assurance Goals
*Mapping ForgeLedger evidence to your specific audit and compliance needs.*

- **Target Frameworks:** Which compliance frameworks or standards are you currently targeting or maintaining? (e.g., SOC 2, ISO 27001, HIPAA, Essential Eight, NIST CSF)
- **Evidence Consumers:** Who will be reviewing the exported evidence packages? (e.g., Internal compliance teams, external auditors, MSP/CSP partners, direct customers)

---

### Next Steps
Once we have this information, we will provide a **ForgeLedger Integration Plan** detailing:
1. The specific adapter/SDK implementation required for your stack.
2. The exact event schemas (`concord.admission_decision`, `warden.llm_call_metadata`, etc.) you will need to emit.
3. The recommended key management and redaction configuration.
4. A representative pilot workflow to validate the integration end-to-end.
