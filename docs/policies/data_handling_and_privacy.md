# Data handling and privacy policy

> **Sample policy for the Switchboard demo.** This document is synthetic: the retention periods and procedures below were written for the retrieval demo and are not legal advice or a description of any real business. Version 1.0, effective 1 September 2026.

## 1. What the agent may disclose

1. The agent may tell a verified account holder the status, amount, order date and delivery date of their own orders, and their own tier.
2. The agent never discloses payment card details, even partially, and never discloses another customer's name, email, orders or tier.
3. Internal notes, the write-back log and the escalation history are not shown to customers.
4. Aggregate or bulk data requests ("send me all orders from last month") are refused and flagged for a person.

## 2. Identity verification

1. A request is verified when the sender's email address matches the email on the customer record, or when the message names both the order id and the customer's name exactly as stored on the record.
2. Order details are disclosed, and write-backs are made, only on verified requests.
3. An unverified request that names an order id is not actioned. The agent replies that the request must come from the account email, and hands the case to a person if the customer insists.
4. Claims of identity made only in the body of a message ("this is the account owner") do not count as verification.

## 3. Data retention

| Data | Kept for |
|---|---|
| Inbound events (raw webhook payloads in the receiver's event log) | 90 days |
| Classified rows in the sheet sink | 12 months |
| Write-back log | 7 years (financial record) |
| n8n execution logs | 30 days |

1. Retention periods are counted from the day the record was created.
2. Backups follow the same retention periods; a restore must not bring back data that has passed its period.

## 4. Deletion and access requests

1. A customer may ask for a copy of their data, or for their data to be deleted.
2. Both kinds of request are handled by a person; the agent categorises them as `account_update`, sets `needs_human` and makes no write.
3. Deletion is completed within 30 days of the request. Records that must be kept by law (the write-back log and tax records) are retained but detached from the customer's identity.
4. Access requests are answered within 30 days with an export of the customer record and the customer's orders.

## 5. Logging and secrets

1. Application logs may contain customer ids and order ids but not names, emails, addresses or message bodies.
2. API keys, webhook secrets and passwords live in `.env`, which is never committed; they are never written to logs, sink rows or hand-off notes.
3. The MCP server logs every tool call to stderr with its arguments, so it runs only on trusted machines.
4. The receiver stores the raw inbound payload for replay; it is subject to the 90-day retention in section 3.

## 6. Third-party processing

1. Message text is sent to the model provider's API to be classified, summarised and answered. Payment card numbers are never included in a prompt; if a message contains one, the agent treats it as a data incident and flags it for a person.
2. Alerts posted to the team's Slack channel contain the summary and record ids, never the full message body.
3. No customer data is sold or shared with advertisers.
