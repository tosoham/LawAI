"""
Sample Legal Data Loader for LawAI
Provides realistic Indian legal content for demo purposes
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class LegalDataLoader:
    """Loads sample legal data for BNS, BNSS, BSA, and SC Judgements"""
    
    @staticmethod
    def get_bns_sections() -> List[Dict[str, Any]]:
        """
        Get sample BNS (Bharatiya Nyaya Sanhita) sections
        
        Returns:
            List of dicts with 'id', 'text', 'metadata'
        """
        sections = [
            {
                'id': 'bns_103',
                'text': '''Section 103 - Punishment for murder
Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.
Explanation: For the purposes of this section, "murder" means the act of causing death with the intention of causing death, or with the intention of causing such bodily injury as is likely to cause death, or with the knowledge that the act is so imminently dangerous that it must in all probability cause death.''',
                'metadata': {
                    'section_number': '103',
                    'title': 'Punishment for murder',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Offences Affecting the Human Body'
                }
            },
            {
                'id': 'bns_302',
                'text': '''Section 302 - Punishment for theft
Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.''',
                'metadata': {
                    'section_number': '302',
                    'title': 'Punishment for theft',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Offences Against Property'
                }
            },
            {
                'id': 'bns_64',
                'text': '''Section 64 - Right of private defence of body
Every person has a right, subject to the restrictions contained in section 65, to defend his own body, and the body of any other person, against any offence affecting the human body.''',
                'metadata': {
                    'section_number': '64',
                    'title': 'Right of private defence of body',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'General Exceptions'
                }
            },
            {
                'id': 'bns_351',
                'text': '''Section 351 - Criminal breach of trust
Whoever, being in any manner entrusted with property, or with any dominion over property, dishonestly misappropriates or converts to his own use that property, or dishonestly uses or disposes of that property in violation of any direction of law prescribing the mode in which such trust is to be discharged, or of any legal contract, express or implied, which he has made touching the discharge of such trust, or wilfully suffers any other person so to do, commits "criminal breach of trust".''',
                'metadata': {
                    'section_number': '351',
                    'title': 'Criminal breach of trust',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Offences Against Property'
                }
            },
            {
                'id': 'bns_115',
                'text': '''Section 115 - Abetment of offence punishable with death or imprisonment for life
Whoever abets the commission of an offence punishable with death or imprisonment for life, shall, if that offence be not committed in consequence of the abetment, and no express provision is made by this Sanhita for the punishment of such abetment, be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.''',
                'metadata': {
                    'section_number': '115',
                    'title': 'Abetment of offence punishable with death or imprisonment for life',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Abetment'
                }
            },
            {
                'id': 'bns_420',
                'text': '''Section 420 - Cheating and dishonestly inducing delivery of property
Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy the whole or any part of a valuable security, or anything which is signed or sealed, and which is capable of being converted into a valuable security, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.''',
                'metadata': {
                    'section_number': '420',
                    'title': 'Cheating and dishonestly inducing delivery of property',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Offences Relating to Documents and Property Marks'
                }
            },
            {
                'id': 'bns_376',
                'text': '''Section 376 - Punishment for rape
Whoever commits rape shall be punished with rigorous imprisonment of either description for a term which shall not be less than ten years, but which may extend to imprisonment for life, and shall also be liable to fine.''',
                'metadata': {
                    'section_number': '376',
                    'title': 'Punishment for rape',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Offences Affecting the Human Body'
                }
            },
            {
                'id': 'bns_499',
                'text': '''Section 499 - Defamation
Whoever, by words either spoken or intended to be read, or by signs or by visible representations, makes or publishes any imputation concerning any person intending to harm, or knowing or having reason to believe that such imputation will harm, the reputation of such person, is said to defame that person.''',
                'metadata': {
                    'section_number': '499',
                    'title': 'Defamation',
                    'act': 'Bharatiya Nyaya Sanhita',
                    'year': '2023',
                    'chapter': 'Of Defamation'
                }
            }
        ]
        return sections
    
    @staticmethod
    def get_bnss_sections() -> List[Dict[str, Any]]:
        """
        Get sample BNSS (Bharatiya Nagarik Suraksha Sanhita) sections
        
        Returns:
            List of dicts with 'id', 'text', 'metadata'
        """
        sections = [
            {
                'id': 'bnss_479',
                'text': '''Section 479 - Bail in non-bailable offences
(1) When any person accused of, or suspected of, the commission of any non-bailable offence is arrested or detained without warrant by an officer in charge of a police station or appears or is brought before a Court other than the High Court or Court of Session, he may be released on bail, but—
(i) such person shall not be so released if there appear reasonable grounds for believing that he has been guilty of an offence punishable with death or imprisonment for life;
(ii) such person shall not be so released if such offence is a cognizable offence and he had been previously convicted of an offence punishable with death, imprisonment for life or imprisonment for seven years or more, or he had been previously convicted on two or more occasions of a non-bailable and cognizable offence.''',
                'metadata': {
                    'section_number': '479',
                    'title': 'Bail in non-bailable offences',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Arrest of Persons'
                }
            },
            {
                'id': 'bnss_482',
                'text': '''Section 482 - Anticipatory bail
(1) Where any person has reason to believe that he may be arrested on accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section that in the event of such arrest, he shall be released on bail; and that Court may, after taking into consideration, inter alia, the following factors, namely:—
(a) the nature and gravity of the accusation;
(b) the antecedents of the applicant including the fact as to whether he has previously undergone imprisonment on conviction by a Court in respect of any cognizable offence;
(c) the possibility of the applicant to flee from justice; and
(d) where the accusation has been made with the object of injuring or humiliating the applicant by having him so arrested,
either reject the application forthwith or issue an interim order for the grant of anticipatory bail.''',
                'metadata': {
                    'section_number': '482',
                    'title': 'Anticipatory bail',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Arrest of Persons'
                }
            },
            {
                'id': 'bnss_154',
                'text': '''Section 154 - Information in cognizable cases
(1) Every information relating to the commission of a cognizable offence, if given orally to an officer in charge of a police station, shall be reduced to writing by him or under his direction, and be read over to the informant; and every such information, whether given in writing or reduced to writing as aforesaid, shall be signed by the person giving it, and the substance thereof shall be entered in a book to be kept by such officer in such form as the State Government may prescribe in this behalf.''',
                'metadata': {
                    'section_number': '154',
                    'title': 'Information in cognizable cases',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Information to the Police and Their Powers to Investigate'
                }
            },
            {
                'id': 'bnss_41',
                'text': '''Section 41 - When police may arrest without warrant
(1) Any police officer may without an order from a Magistrate and without a warrant, arrest any person—
(a) who has been concerned in any cognizable offence, or against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists, of his having been so concerned;
(b) who has in his possession without lawful excuse, the burden of proving which excuse shall lie on such person, any implement of house-breaking;
(c) who has been proclaimed as an offender either under this Sanhita or by order of the State Government;
(d) in whose possession anything is found which may reasonably be suspected to be stolen property and who may reasonably be suspected of having committed an offence with reference to such thing.''',
                'metadata': {
                    'section_number': '41',
                    'title': 'When police may arrest without warrant',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Arrest of Persons'
                }
            },
            {
                'id': 'bnss_167',
                'text': '''Section 167 - Procedure when investigation cannot be completed in twenty-four hours
(1) Whenever any person is arrested and detained in custody, and it appears that the investigation cannot be completed within the period of twenty-four hours fixed by section 57, and there are grounds for believing that the accusation or information is well-founded, the officer in charge of the police station or the police officer making the investigation, if he is not below the rank of sub-inspector, shall forthwith transmit to the nearest Judicial Magistrate a copy of the entries in the diary hereinafter prescribed relating to the case, and shall at the same time forward the accused to such Magistrate.''',
                'metadata': {
                    'section_number': '167',
                    'title': 'Procedure when investigation cannot be completed in twenty-four hours',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Information to the Police and Their Powers to Investigate'
                }
            },
            {
                'id': 'bnss_313',
                'text': '''Section 313 - Power to examine the accused
(1) For the purpose of enabling the accused personally to explain any circumstances appearing in the evidence against him, the Court—
(a) may at any stage of any inquiry or trial, without previously warning the accused, put such questions to him as the Court considers necessary;
(b) shall, after the witnesses for the prosecution have been examined and before he is called on for his defence, question him generally on the case.''',
                'metadata': {
                    'section_number': '313',
                    'title': 'Power to examine the accused',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Trial'
                }
            },
            {
                'id': 'bnss_125',
                'text': '''Section 125 - Order for maintenance of wives, children and parents
(1) If any person having sufficient means neglects or refuses to maintain—
(a) his wife, unable to maintain herself, or
(b) his legitimate or illegitimate minor child, whether married or not, unable to maintain itself, or
(c) his legitimate or illegitimate child (not being a married daughter) who has attained majority, where such child is, by reason of any physical or mental abnormality or injury unable to maintain itself, or
(d) his father or mother, unable to maintain himself or herself,
a Magistrate of the first class may, upon proof of such neglect or refusal, order such person to make a monthly allowance for the maintenance of his wife or such child, father or mother, at such monthly rate not exceeding five hundred rupees in the whole, as such Magistrate thinks fit.''',
                'metadata': {
                    'section_number': '125',
                    'title': 'Order for maintenance of wives, children and parents',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023',
                    'chapter': 'Of Maintenance of Wives, Children and Parents'
                }
            }
        ]
        return sections
    
    @staticmethod
    def get_bsa_sections() -> List[Dict[str, Any]]:
        """
        Get sample BSA (Bharatiya Sakshya Adhiniyam) sections
        
        Returns:
            List of dicts with 'id', 'text', 'metadata'
        """
        sections = [
            {
                'id': 'bsa_2',
                'text': '''Section 2 - Definitions
In this Adhiniyam, unless the context otherwise requires,—
(1) "evidence" means and includes—
(a) all statements which the Court permits or requires to be made before it by witnesses, in relation to matters of fact under inquiry; such statements are called oral evidence;
(b) all documents including electronic or digital records produced for the inspection of the Court; such documents are called documentary evidence;
(2) "fact" means and includes—
(a) any thing, state of things, or relation of things, capable of being perceived by the senses;
(b) any mental condition of which any person is conscious.''',
                'metadata': {
                    'section_number': '2',
                    'title': 'Definitions',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Preliminary'
                }
            },
            {
                'id': 'bsa_3',
                'text': '''Section 3 - Evidence may be given of facts in issue and relevant facts
Evidence may be given in any suit or proceeding of the existence or non-existence of every fact in issue and of such other facts as are hereinafter declared to be relevant, and of no others.
Explanation: This section shall not enable any person to give evidence of a fact which he is disentitled to prove by any provision of the law for the time being in force relating to Civil Procedure.''',
                'metadata': {
                    'section_number': '3',
                    'title': 'Evidence may be given of facts in issue and relevant facts',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of the Relevancy of Facts'
                }
            },
            {
                'id': 'bsa_24',
                'text': '''Section 24 - Confession caused by inducement, threat or promise
A confession made by an accused person is irrelevant in a criminal proceeding, if the making of the confession appears to the Court to have been caused by any inducement, threat or promise having reference to the charge against the accused person, proceeding from a person in authority and sufficient, in the opinion of the Court, to give the accused person grounds which would appear to him reasonable for supposing that by making it he would gain any advantage or avoid any evil of a temporal nature in reference to the proceedings against him.''',
                'metadata': {
                    'section_number': '24',
                    'title': 'Confession caused by inducement, threat or promise',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of Admissions and Confessions'
                }
            },
            {
                'id': 'bsa_45',
                'text': '''Section 45 - Opinions of experts
When the Court has to form an opinion upon a point of foreign law, or of science or art, or as to identity of handwriting or finger impressions, the opinions upon that point of persons specially skilled in such foreign law, science or art, or in questions as to identity of handwriting or finger impressions are relevant facts. Such persons are called experts.''',
                'metadata': {
                    'section_number': '45',
                    'title': 'Opinions of experts',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of the Relevancy of Facts'
                }
            },
            {
                'id': 'bsa_65',
                'text': '''Section 65 - Proof of electronic records
(1) Notwithstanding anything contained in this Adhiniyam, any information contained in an electronic record which is printed on a paper, stored, recorded or copied in optical or magnetic media produced by a computer (hereinafter referred to as the computer output) shall be deemed to be also a document, if the conditions mentioned in this section are satisfied in relation to the information and computer in question and shall be admissible in any proceedings, without further proof or production of the original, as evidence of any contents of the original or of any fact stated therein of which direct evidence would be admissible.''',
                'metadata': {
                    'section_number': '65',
                    'title': 'Proof of electronic records',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of Documentary Evidence'
                }
            },
            {
                'id': 'bsa_101',
                'text': '''Section 101 - Burden of proof
Whoever desires any Court to give judgment as to any legal right or liability dependent on the existence of facts which he asserts, must prove that those facts exist. When a person is bound to prove the existence of any fact, it is said that the burden of proof lies on that person.''',
                'metadata': {
                    'section_number': '101',
                    'title': 'Burden of proof',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of the Burden of Proof'
                }
            },
            {
                'id': 'bsa_118',
                'text': '''Section 118 - Who may testify
All persons shall be competent to testify unless the Court considers that they are prevented from understanding the questions put to them, or from giving rational answers to those questions, by reason of tender years, extreme old age, disease, whether of body or mind, or any other cause of the same kind.
Explanation: A lunatic is not incompetent to testify, unless he is prevented by his lunacy from understanding the questions put to him and giving rational answers to them.''',
                'metadata': {
                    'section_number': '118',
                    'title': 'Who may testify',
                    'act': 'Bharatiya Sakshya Adhiniyam',
                    'year': '2023',
                    'chapter': 'Of Witnesses'
                }
            }
        ]
        return sections
    
    @staticmethod
    def get_sc_judgements() -> List[Dict[str, Any]]:
        """
        Get sample Supreme Court judgements
        
        Returns:
            List of dicts with 'id', 'text', 'metadata'
        """
        judgements = [
            {
                'id': 'sc_arnesh_kumar_2014',
                'text': '''Arnesh Kumar vs State of Bihar & Anr (2014) 8 SCC 273

SUMMARY: This landmark judgment laid down mandatory guidelines for arrest in cases punishable with imprisonment up to 7 years. The Supreme Court held that arrest should not be made in a routine manner and police officers must satisfy themselves about the necessity of arrest.

KEY HOLDINGS:
1. Police officers must record reasons for arrest in the case diary
2. Magistrate must apply mind to the necessity of arrest while authorizing detention
3. Arrest should be the last option, not the first resort
4. Failure to comply may result in departmental action

RATIO DECIDENDI: The power of arrest is a draconian power which should be exercised with great care and caution. Arrest brings humiliation, curtails freedom and casts scars forever. Therefore, law requires strict compliance with procedural safeguards.

RELEVANT SECTIONS: BNSS Section 41, 41A (arrest procedures)

This judgment is frequently cited in bail applications and anticipatory bail matters to argue against unnecessary arrests.''',
                'metadata': {
                    'case_name': 'Arnesh Kumar vs State of Bihar',
                    'citation': '(2014) 8 SCC 273',
                    'year': '2014',
                    'court': 'Supreme Court of India',
                    'bench': 'Division Bench',
                    'subject': 'Arrest Guidelines',
                    'relevant_sections': 'BNSS 41, 41A'
                }
            },
            {
                'id': 'sc_sushila_aggarwal_2020',
                'text': '''Sushila Aggarwal & Ors vs State (NCT of Delhi) & Anr (2020) 5 SCC 1

SUMMARY: This case dealt with the scope and limitations of anticipatory bail under Section 438 CrPC (now BNSS 482). The Supreme Court clarified that anticipatory bail can be granted even after arrest and that courts should not impose unnecessary conditions.

KEY HOLDINGS:
1. Anticipatory bail can be granted even after arrest if the person has not been remanded to judicial custody
2. Courts should not impose onerous conditions that defeat the purpose of bail
3. The distinction between pre-arrest and post-arrest bail is not always rigid
4. Personal liberty is a fundamental right that deserves protection

RATIO DECIDENDI: The object of anticipatory bail is to prevent harassment through arrest. Courts must balance individual liberty with the needs of investigation while granting anticipatory bail.

RELEVANT SECTIONS: BNSS Section 482 (anticipatory bail)

This judgment is crucial for anticipatory bail applications and understanding the scope of pre-arrest protection.''',
                'metadata': {
                    'case_name': 'Sushila Aggarwal vs State (NCT of Delhi)',
                    'citation': '(2020) 5 SCC 1',
                    'year': '2020',
                    'court': 'Supreme Court of India',
                    'bench': 'Three Judge Bench',
                    'subject': 'Anticipatory Bail',
                    'relevant_sections': 'BNSS 482'
                }
            },
            {
                'id': 'sc_satender_kumar_2011',
                'text': '''Satender Kumar Antil vs Central Bureau of Investigation (2022) 10 SCC 51

SUMMARY: This comprehensive judgment by a three-judge bench laid down detailed guidelines for grant of bail in serious offences. The Court emphasized that bail is the rule and jail is the exception.

KEY HOLDINGS:
1. Bail is the rule, jail is the exception - even in serious offences
2. Courts must consider: nature of accusation, severity of punishment, character of evidence, circumstances peculiar to accused, larger interest of public/State
3. Prolonged incarceration before trial violates Article 21
4. Bail conditions should be reasonable and not punitive
5. Economic offences may require different considerations

RATIO DECIDENDI: Personal liberty is sacrosanct and deprivation thereof must be founded on the most serious considerations relevant to the welfare objectives of society specified in the Constitution.

RELEVANT SECTIONS: BNSS Sections 479, 482 (bail provisions)

This is the leading authority on bail jurisprudence in India and is cited in virtually every bail application.''',
                'metadata': {
                    'case_name': 'Satender Kumar Antil vs CBI',
                    'citation': '(2022) 10 SCC 51',
                    'year': '2022',
                    'court': 'Supreme Court of India',
                    'bench': 'Three Judge Bench',
                    'subject': 'Bail Guidelines',
                    'relevant_sections': 'BNSS 479, 482'
                }
            },
            {
                'id': 'sc_lalita_kumari_2014',
                'text': '''Lalita Kumari vs Government of Uttar Pradesh (2014) 2 SCC 1

SUMMARY: This Constitution Bench judgment made registration of FIR mandatory for all cognizable offences. The Court held that police have no discretion in registering FIR when information about cognizable offence is received.

KEY HOLDINGS:
1. Registration of FIR is mandatory under Section 154 CrPC (now BNSS 154) for cognizable offences
2. Police have no power to conduct preliminary inquiry before registering FIR
3. Exceptions: matrimonial disputes, commercial offences, medical negligence cases, corruption cases - preliminary inquiry permitted
4. Refusal to register FIR is a violation of law

RATIO DECIDENDI: The mandate of Section 154 is clear - information about cognizable offence must be registered immediately. Any delay or discretion defeats the purpose of criminal justice system.

RELEVANT SECTIONS: BNSS Section 154 (FIR registration)

This judgment is crucial for understanding FIR registration procedures and challenging illegal refusal to register FIR.''',
                'metadata': {
                    'case_name': 'Lalita Kumari vs Govt of UP',
                    'citation': '(2014) 2 SCC 1',
                    'year': '2014',
                    'court': 'Supreme Court of India',
                    'bench': 'Constitution Bench',
                    'subject': 'FIR Registration',
                    'relevant_sections': 'BNSS 154'
                }
            },
            {
                'id': 'sc_state_of_punjab_2005',
                'text': '''State of Punjab vs Balbir Singh (2005) 12 SCC 437

SUMMARY: This case dealt with the evidentiary value of dying declarations and the circumstances under which they can be relied upon for conviction.

KEY HOLDINGS:
1. Dying declaration can be the sole basis for conviction if it inspires full confidence
2. No corroboration required if dying declaration is clear, consistent and made voluntarily
3. Court must be satisfied that deceased was in fit state of mind
4. Multiple dying declarations - court should consider most reliable one
5. Certification by doctor about mental fitness is desirable but not mandatory

RATIO DECIDENDI: A dying declaration stands on the same footing as any other piece of evidence and has to be judged in the light of surrounding circumstances and with reference to principles governing appreciation of evidence.

RELEVANT SECTIONS: BSA Section 32 (dying declarations)

This judgment is the leading authority on dying declarations and is cited in all murder trials involving dying declarations.''',
                'metadata': {
                    'case_name': 'State of Punjab vs Balbir Singh',
                    'citation': '(2005) 12 SCC 437',
                    'year': '2005',
                    'court': 'Supreme Court of India',
                    'bench': 'Division Bench',
                    'subject': 'Dying Declaration',
                    'relevant_sections': 'BSA 32'
                }
            }
        ]
        return judgements
    
    def load_all_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load all sample legal data
        
        Returns:
            Dict with keys: 'bns', 'bnss', 'bsa', 'sc_judgements'
        """
        return {
            'bns': self.get_bns_sections(),
            'bnss': self.get_bnss_sections(),
            'bsa': self.get_bsa_sections(),
            'sc_judgements': self.get_sc_judgements()
        }

# Made with Bob
