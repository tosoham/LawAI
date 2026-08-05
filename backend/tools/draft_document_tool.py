"""
Draft Document Tool

Generate legal documents like bail applications, petitions, and notices.
"""

import asyncio
import re

from services.llm_service import LLMService

from .base_tool import BaseTool, ToolParameter, ToolResult

# Matches a whole response wrapped in one markdown fence, e.g. ```plaintext ... ```
_FENCED_RESPONSE = re.compile(
    r"\A\s*```[^\n]*\n(?P<body>.*?)\n?```\s*\Z",
    re.DOTALL,
)


def _strip_code_fence(document: str) -> str:
    """
    Unwrap a document the model returned inside a markdown code fence.

    Asking it not to do this helps but does not eliminate it, and the fence is
    not cosmetic: the .docx export writes the text verbatim, so a stray
    ```plaintext ends up as the first line of a document filed in court.
    Only a fence wrapping the *entire* response is removed -- one around a
    quoted extract inside a document is left alone.
    """
    match = _FENCED_RESPONSE.match(document)
    return match.group("body") if match else document


class DraftDocumentTool(BaseTool):
    """
    Tool for generating legal documents.

    Supports bail applications, petitions, legal notices, agreements and
    affidavits. Uses specialized prompts for each document type.
    """

    def __init__(self, llm_service: LLMService):
        """
        Initialize draft document tool.

        Args:
            llm_service: LLM service instance
        """
        super().__init__()
        self.llm_service = llm_service
        self.examples = [
            "Draft bail application for BNS 103 case",
            "Generate petition for anticipatory bail",
            "Create legal notice for breach of contract"
        ]

        # Document templates
        self.templates = {
            "bail_application": self._get_bail_template(),
            "petition": self._get_petition_template(),
            "notice": self._get_notice_template(),
            "agreement": self._get_agreement_template(),
            "affidavit": self._get_affidavit_template()
        }

    @property
    def name(self) -> str:
        return "draft_document"

    @property
    def description(self) -> str:
        return "Generate legal documents (bail applications, petitions, notices)"

    @property
    def parameters(self) -> dict[str, ToolParameter]:
        return {
            "document_type": ToolParameter(
                name="document_type",
                type="string",
                description=(
                    "Type of document "
                    "(bail_application|petition|notice|agreement|affidavit)"
                ),
                required=True
            ),
            "case_details": ToolParameter(
                name="case_details",
                type="dict",
                description="Case details (accused_name, fir_number, sections, facts, etc.)",
                required=True
            )
        }

    def _get_bail_template(self) -> str:
        """Get bail application template"""
        return """Draft a comprehensive bail application with the following structure:

IN THE COURT OF [COURT NAME]
[LOCATION]

BAIL APPLICATION UNDER SECTION 479/482 BNSS

In the matter of:
[ACCUSED NAME] ... Applicant

Versus

STATE OF [STATE] ... Respondent

MOST RESPECTFULLY SHOWETH:

1. That the applicant has been arrested in connection with FIR No. [FIR_NUMBER] under Sections [SECTIONS] at [POLICE_STATION].

2. BRIEF FACTS:
[FACTS]

3. GROUNDS FOR BAIL:
   a) The applicant is innocent and has been falsely implicated
   b) The applicant has deep roots in society and will not abscond
   c) The applicant is ready to abide by any conditions imposed by this Hon'ble Court
   d) The applicant's continued detention is not required for investigation
   e) [ADDITIONAL_GROUNDS]

4. LEGAL PROVISIONS:
[RELEVANT_SECTIONS_ANALYSIS]

5. PRAYER:
In light of the above, it is most respectfully prayed that this Hon'ble Court may be pleased to:
   a) Grant regular/anticipatory bail to the applicant
   b) Release the applicant on such terms and conditions as this Hon'ble Court deems fit
   c) Pass any other order as this Hon'ble Court deems fit

AND FOR THIS ACT OF KINDNESS, THE APPLICANT SHALL DUTY BOUND FOREVER PRAY.

Place: [PLACE]
Date: [DATE]

[ADVOCATE NAME]
Advocate for Applicant
Enrolment No.: [ENROLMENT_NO]"""

    def _get_petition_template(self) -> str:
        """Get petition template"""
        return """Draft a comprehensive petition with the following structure:

IN THE [COURT NAME]
AT [LOCATION]

[PETITION TYPE]

[PETITIONER NAME] ... Petitioner

Versus

[RESPONDENT NAME] ... Respondent

MOST RESPECTFULLY SHOWETH:

1. PARTIES:
[PARTY_DETAILS]

2. FACTS:
[DETAILED_FACTS]

3. CAUSE OF ACTION:
[CAUSE_OF_ACTION]

4. LEGAL GROUNDS:
[LEGAL_GROUNDS]

5. RELIEF SOUGHT:
[RELIEF_DETAILS]

6. PRAYER:
In light of the above facts and circumstances, it is most respectfully prayed that this Hon'ble Court may be pleased to:
[SPECIFIC_PRAYERS]

AND FOR THIS ACT OF KINDNESS, THE PETITIONER SHALL DUTY BOUND FOREVER PRAY.

Place: [PLACE]
Date: [DATE]

[ADVOCATE NAME]
Advocate for Petitioner"""

    def _get_notice_template(self) -> str:
        """Get legal notice template"""
        return """Draft a legal notice with the following structure:

LEGAL NOTICE

To,
[RECIPIENT_NAME]
[RECIPIENT_ADDRESS]

Dear Sir/Madam,

SUBJECT: [SUBJECT]

Under instructions from and on behalf of my client [CLIENT_NAME], I hereby serve you with this legal notice for the following reasons:

1. FACTS:
[DETAILED_FACTS]

2. LEGAL POSITION:
[LEGAL_GROUNDS]

3. DEMAND:
[SPECIFIC_DEMANDS]

4. NOTICE:
You are hereby called upon to [SPECIFIC_ACTION] within 15 days from the receipt of this notice, failing which my client shall be constrained to initiate appropriate legal proceedings against you at your risk as to costs and consequences.

Please treat this as urgent and final notice.

Yours faithfully,

[ADVOCATE NAME]
Advocate
[ADDRESS]
Date: [DATE]"""

    def _get_agreement_template(self) -> str:
        """Get agreement/contract template"""
        return """Draft a comprehensive agreement with the following structure:

[AGREEMENT TITLE]

This Agreement is made and executed at [PLACE] on this [DATE].

BETWEEN

[FIRST_PARTY_NAME], [FIRST_PARTY_DESCRIPTION], residing at/having its registered
office at [FIRST_PARTY_ADDRESS] (hereinafter referred to as the "First Party",
which expression shall, unless repugnant to the context, include its successors
and permitted assigns) of the ONE PART;

AND

[SECOND_PARTY_NAME], [SECOND_PARTY_DESCRIPTION], residing at/having its registered
office at [SECOND_PARTY_ADDRESS] (hereinafter referred to as the "Second Party",
which expression shall, unless repugnant to the context, include its successors
and permitted assigns) of the OTHER PART.

WHEREAS:
[RECITALS]

NOW THEREFORE, in consideration of the mutual covenants contained herein, the
parties agree as follows:

1. DEFINITIONS AND INTERPRETATION:
[DEFINITIONS]

2. SCOPE AND OBLIGATIONS:
[SCOPE_OF_AGREEMENT]

3. CONSIDERATION AND PAYMENT TERMS:
[PAYMENT_TERMS]

4. TERM AND RENEWAL:
[TERM_DETAILS]

5. REPRESENTATIONS AND WARRANTIES:
[REPRESENTATIONS]

6. CONFIDENTIALITY:
[CONFIDENTIALITY_TERMS]

7. INDEMNITY:
[INDEMNITY_TERMS]

8. TERMINATION:
[TERMINATION_CLAUSES]

9. DISPUTE RESOLUTION AND ARBITRATION:
Any dispute arising out of or in connection with this Agreement shall be referred
to arbitration under the Arbitration and Conciliation Act, 1996. The seat of
arbitration shall be [SEAT].

10. GOVERNING LAW AND JURISDICTION:
This Agreement shall be governed by the laws of India and the courts at [JURISDICTION]
shall have exclusive jurisdiction.

11. MISCELLANEOUS:
[MISCELLANEOUS_CLAUSES]

IN WITNESS WHEREOF, the parties have executed this Agreement on the day, month and
year first written above.

For and on behalf of                    For and on behalf of
[FIRST_PARTY_NAME]                      [SECOND_PARTY_NAME]

_____________________                   _____________________
(Authorised Signatory)                  (Authorised Signatory)

WITNESSES:
1. _____________________
2. _____________________"""

    def _get_affidavit_template(self) -> str:
        """
        Get affidavit template.

        Sworn on oath, so the wording is deliberately conservative: the deponent
        must distinguish personal knowledge from information believed to be true,
        and nothing may be asserted that the deponent cannot verify.
        """
        return """Draft an affidavit with the following structure:

IN THE COURT OF [COURT NAME]
[LOCATION]

[CASE TITLE / MATTER]
[CASE NUMBER, if any]

AFFIDAVIT OF [DEPONENT_NAME]

I, [DEPONENT_NAME], aged about [AGE] years, [OCCUPATION], son/daughter/wife of
[PARENT_OR_SPOUSE_NAME], resident of [ADDRESS], do hereby solemnly affirm and
state on oath as follows:

1. That I am the [CAPACITY - e.g. applicant / respondent / authorised
   representative] in the above-mentioned matter and am competent to swear to
   this affidavit.

2. That the present affidavit is being filed for the purpose of [PURPOSE].

3. FACTS DEPOSED TO:
[FACTS]

4. That the contents of paragraphs [PARAGRAPH_NUMBERS] are true to my personal
   knowledge, and the contents of paragraphs [PARAGRAPH_NUMBERS] are based on
   information received and believed by me to be true.

5. That I have not suppressed any material fact, and no part of this affidavit
   is false.

6. [ADDITIONAL_AVERMENTS]

DEPONENT

VERIFICATION:

I, the above-named deponent, do hereby verify that the contents of the above
affidavit are true and correct to the best of my knowledge and belief, that no
part of it is false and that nothing material has been concealed therefrom.

Verified at [PLACE] on this [DATE].

DEPONENT

Solemnly affirmed before me on this [DATE].

_____________________
(Oath Commissioner / Notary Public)"""

    def _create_prompt(self, document_type: str, case_details: dict) -> str:
        """
        Create prompt for document generation.

        Args:
            document_type: Type of document
            case_details: Case information

        Returns:
            Formatted prompt
        """
        template = self.templates.get(document_type, "")

        prompt = f"""You are an expert legal document drafter specializing in Indian law.

TASK: Generate a professional {document_type.replace('_', ' ')} based on the template and case details provided.

TEMPLATE:
{template}

CASE DETAILS:
{self._format_case_details(case_details)}

INSTRUCTIONS:
1. Follow the template structure exactly
2. Fill placeholders ONLY from the case details above
3. NEVER invent facts about a person or a case. If the details do not supply
   something the template asks for -- an age, an occupation, a parent's name, a
   date, a court, a case number -- leave the bracketed placeholder in place for
   the advocate to complete. A document with [AGE] left blank is usable; one
   asserting an age that nobody supplied is not.
4. Do not invent section numbers or case citations. Cite only provisions you are
   certain of, and omit rather than guess.
5. Use proper legal language and terminology
6. Use proper formatting with clear sections and numbering
7. Output the document text only -- no commentary, and no markdown code fences

Generate the complete document now:"""

        return prompt

    def _format_case_details(self, case_details: dict) -> str:
        """Format case details for prompt"""
        formatted = []
        for key, value in case_details.items():
            formatted.append(f"- {key.replace('_', ' ').title()}: {value}")
        return "\n".join(formatted)

    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute document drafting.

        Args:
            document_type: Type of document to draft
            case_details: Case information

        Returns:
            ToolResult with drafted document
        """
        try:
            document_type = kwargs.get("document_type")
            case_details = kwargs.get("case_details", {})

            if not document_type:
                return ToolResult(
                    success=False,
                    error="document_type is required"
                )

            if document_type not in self.templates:
                return ToolResult(
                    success=False,
                    error=f"Unsupported document type: {document_type}. Supported: {list(self.templates.keys())}"
                )

            if not case_details:
                return ToolResult(
                    success=False,
                    error="case_details are required"
                )

            self.logger.info(f"Drafting {document_type} with {len(case_details)} details")

            # Create prompt
            prompt = self._create_prompt(document_type, case_details)

            # Generate document (offloaded so the event loop is not blocked)
            document = await asyncio.to_thread(self.llm_service.generate, prompt=prompt)
            document = _strip_code_fence(document)

            # Add metadata
            result_data = {
                "document": document,
                "document_type": document_type,
                "case_details": case_details,
                "disclaimer": "This is an AI-generated legal document. Please have it reviewed by a qualified lawyer before filing."
            }

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "tool": self.name,
                    "document_type": document_type,
                    "document_length": len(document)
                }
            )

        except Exception as e:
            self.logger.error(f"Document drafting failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Document drafting failed: {e!s}"
            )
