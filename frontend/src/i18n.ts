/**
 * Interface-chrome strings only — English and Hindi. This never touches the
 * substance of an answer (that comes from the backend, in whatever language
 * the question was asked); it only translates the shell around it: labels,
 * placeholders, buttons, hints. Swapping `uiLang` re-renders the whole shell
 * instantly, no reload.
 */

export type UiLang = "en" | "hi";

export interface Example {
  labelEn: string;
  labelHi: string;
  questionEn: string;
  questionHi: string;
  mode: "ask" | "compare";
}

export const EXAMPLES: Example[] = [
  {
    labelEn: "The flagship",
    labelHi: "मुख्य प्रश्न",
    mode: "ask",
    questionEn: "Can a classical churna from a First Schedule text be patented?",
    questionHi: "क्या प्रथम अनुसूची ग्रंथ के एक शास्त्रीय चूर्ण को पेटेंट कराया जा सकता है?",
  },
  {
    labelEn: "Registration process",
    labelHi: "पंजीकरण प्रक्रिया",
    mode: "ask",
    questionEn: "How do I register a Geographical Indication for an Ayurvedic product?",
    questionHi: "आयुर्वेदिक उत्पाद के लिए भौगोलिक संकेत (GI) कैसे पंजीकृत करूँ?",
  },
  {
    labelEn: "Biodiversity / ABS",
    labelHi: "जैव विविधता / ABS",
    mode: "ask",
    questionEn: "What is Access and Benefit Sharing and when do I need NBA approval?",
    questionHi: "एक्सेस एंड बेनिफिट शेयरिंग क्या है और मुझे NBA अनुमोदन कब चाहिए?",
  },
  {
    labelEn: "Compare categories",
    labelHi: "श्रेणियों की तुलना",
    mode: "compare",
    questionEn:
      "An ashwagandha churna made to a First Schedule formula, but standardised for withanolide content",
    questionHi:
      "अश्वगंधा चूर्ण, प्रथम अनुसूची सूत्र के अनुसार बना है, पर विथेनोलाइड सामग्री के लिए मानकीकृत",
  },
];

export const FEATURE_CHIPS: { en: string; hi: string }[] = [
  { en: "Cited to Act & section", hi: "अधिनियम व धारा से उद्धृत" },
  { en: "Confidence-scored", hi: "विश्वास-स्कोर सहित" },
  { en: "English & Hindi", hi: "अंग्रेज़ी और हिंदी" },
  { en: "ABS & TKDL aware", hi: "ABS और TKDL जागरूक" },
];

type Dict = Record<string, string>;

export const STRINGS: Record<UiLang, Dict> = {
  en: {
    // Site navigation. The workspace is one destination among several now: the
    // landing page, the treaty routes and the registry links are pages in their
    // own right rather than panels buried inside a consultation.
    navHome: "Home",
    navConsult: "Consult",
    navCompare: "Compare",
    navExport: "Export readiness",
    navTreaties: "Treaty routes",
    navSources: "Sources",
    exportBriefing: "Print briefing",
    exportBriefingHint: "Open this consultation as a printable opinion sheet",
    tagline: "Source-cited IP & regulatory guidance for Ayurveda",
    sectionMode: "What would you like to do?",
    modeAsk: "Ask a question",
    modeCompare: "Compare categories",
    modeCompareJurisdictions: "Compare jurisdictions",
    compareJurisdictionsHint:
      "India and the international instruments, answered separately and then compared.",
    sideNational: "India",
    sideInternational: "International",
    sideSilent: "no finding on this point",
    revealOther: "Also show the {side} position",
    revealingOther: "Answering from {side} sources…",
    compareBoth: "Compare the two",
    comparingBoth: "Comparing the two answers…",
    comparisonHeading: "How the two compare",
    comparisonGuard: "Comparison guard",
    comparisonUnavailable: "Comparison unavailable",
    comparingJurisdictionsStage: "Answering both jurisdictions separately…",
    sectionJurisdiction: "Jurisdiction",
    sectionStyle: "Wording",
    styleLegal: "Legal terms",
    stylePlain: "Simple terms",
    styleLegalNote: "Statutory wording, as a practitioner would put it.",
    stylePlainNote:
      "Same findings and the same sources, in everyday words.",
    nextStepsTitle: "What this means next",
    nextStepsAsk: "Suggest next steps",
    nextStepsThinking: "Working out what applies…",
    nextStepsNone: "Nothing to act on here — this question is answered above.",
    nextStepsGuard: "Guidance guard",
    jurisdictionIndia: "India",
    jurisdictionIntl: "International",
    jurisdictionIntlActive:
      "Answering from international instruments only (TRIPS, CBD/Nagoya, WIPO). Indian law is a separate corpus.",
    jurisdictionIntlUnavailable:
      "The international corpus is not loaded, so this cannot be answered from treaty sources yet.",
    jurisdictionIntlNote:
      "International coverage is not available yet — the corpus holds Indian law only.",
    jurisdictionIndiaNote: "Answer from Indian law.",
    sectionPrivacy: "Privacy",
    saveQuestion: "Save my question text",
    saveQuestionHint:
      "Keeps the text of your question in this machine's local audit log. The system always records what it decided, without your question text.",
    disclaimer:
      "This is an informational research tool, not legal advice. Verify against the official source before relying on it.",
    jurisdictionBadge: "National · India",
    statusOnline: "provisions indexed",
    statusOffline: "Backend offline",
    statusConnecting: "Connecting to the corpus…",
    endSession: "End session",
    newConsultation: "New consultation",
    consultations: "Consultations",
    questionsCount: "questions",
    questionCount: "question",
    untitledSession: "New consultation",
    deleteSession: "Remove this consultation",
    deleteAll: "Delete all",
    deleteAllConfirm: "Delete all saved consultations?",
    deleteAllYes: "Delete everything",
    deleteAllNo: "Keep them",
    emptyTitle: "Ask about protecting or commercialising an Ayurvedic product.",
    emptySubtitle:
      "Every answer is built only from cited Indian statutes, rules and registry records — and shows how well-supported it is. When the corpus cannot answer, it says so rather than guessing.",
    tryAsking: "Try asking",
    placeholderAsk: "e.g. Can a classical churna from a First Schedule text be patented?",
    placeholderCompare: "e.g. A herbal syrup using classical ingredients but my own ratios",
    placeholderClarify: "Type your answer…",
    hintEnter: "Enter to ask · Shift + Enter for a new line",
    hintCompare: "Describe a product — see how each category treats it",
    infoNotAdvice: "Information, not legal advice",
    sendAsk: "Ask",
    sendCompare: "Compare",
    sendLoading: "Consulting…",
    stop: "Stop",
    micTooltip: "Voice input",
    micLangTooltip: "Voice input language",
    replyingTo: "Replying to",
    sessionCount: "in this session",
    couldNotComplete: "Could not complete",
    dismiss: "Dismiss",
    classifyingStage: "Classifying, retrieving provisions, verifying citations…",
    comparingStage: "Retrieving provisions, contrasting each category…",
    menu: "Menu",
  },
  hi: {
    navHome: "मुख्य",
    navConsult: "परामर्श",
    navCompare: "तुलना",
    navExport: "निर्यात तत्परता",
    navTreaties: "संधि मार्ग",
    navSources: "स्रोत",
    exportBriefing: "ब्रीफ़िंग प्रिंट करें",
    exportBriefingHint: "इस परामर्श को मुद्रण-योग्य राय-पत्र के रूप में खोलें",
    tagline: "आयुर्वेद के लिए स्रोत-उद्धृत आईपी व नियामक मार्गदर्शन",
    sectionMode: "आप क्या करना चाहेंगे?",
    modeAsk: "प्रश्न पूछें",
    modeCompare: "श्रेणियों की तुलना करें",
    modeCompareJurisdictions: "क्षेत्राधिकार तुलना",
    compareJurisdictionsHint:
      "भारत और अंतरराष्ट्रीय दस्तावेज़ — अलग-अलग उत्तर, फिर तुलना।",
    sideNational: "भारत",
    sideInternational: "अंतरराष्ट्रीय",
    sideSilent: "इस बिंदु पर कोई निष्कर्ष नहीं",
    revealOther: "{side} स्थिति भी दिखाएँ",
    revealingOther: "{side} स्रोतों से उत्तर…",
    compareBoth: "दोनों की तुलना करें",
    comparingBoth: "दोनों उत्तरों की तुलना…",
    comparisonHeading: "दोनों की तुलना",
    comparisonGuard: "तुलना सुरक्षा जाँच",
    comparisonUnavailable: "तुलना उपलब्ध नहीं",
    comparingJurisdictionsStage: "दोनों क्षेत्राधिकारों के अलग-अलग उत्तर…",
    sectionJurisdiction: "क्षेत्राधिकार",
    sectionStyle: "शैली",
    styleLegal: "विधिक शब्द",
    stylePlain: "सरल शब्द",
    styleLegalNote: "वैधानिक शब्दावली, जैसे कोई अधिवक्ता कहे।",
    stylePlainNote: "वही निष्कर्ष और वही स्रोत, सरल शब्दों में।",
    nextStepsTitle: "आगे क्या करें",
    nextStepsAsk: "अगले कदम सुझाएँ",
    nextStepsThinking: "लागू नियम देखे जा रहे हैं…",
    nextStepsNone: "यहाँ करने को कुछ नहीं — उत्तर ऊपर है।",
    nextStepsGuard: "मार्गदर्शन जाँच",
    jurisdictionIndia: "भारत",
    jurisdictionIntl: "अंतरराष्ट्रीय",
    jurisdictionIntlActive:
      "उत्तर केवल अंतरराष्ट्रीय दस्तावेज़ों (TRIPS, CBD/नागोया, WIPO) से; भारतीय विधि अलग संग्रह है।",
    jurisdictionIntlUnavailable:
      "अंतरराष्ट्रीय संग्रह लोड नहीं है।",
    jurisdictionIntlNote:
      "अंतरराष्ट्रीय कवरेज अभी उपलब्ध नहीं है — कॉर्पस में केवल भारतीय कानून है।",
    jurisdictionIndiaNote: "भारतीय कानून के अनुसार उत्तर।",
    sectionPrivacy: "गोपनीयता",
    saveQuestion: "मेरे प्रश्न का टेक्स्ट सहेजें",
    saveQuestionHint:
      "आपके प्रश्न का टेक्स्ट इस मशीन के स्थानीय ऑडिट लॉग में रखा जाता है। सिस्टम हमेशा यह दर्ज करता है कि उसने क्या तय किया, आपके प्रश्न के टेक्स्ट के बिना भी।",
    disclaimer:
      "यह एक सूचनात्मक शोध उपकरण है, कानूनी सलाह नहीं। भरोसा करने से पहले आधिकारिक स्रोत से पुष्टि करें।",
    jurisdictionBadge: "राष्ट्रीय · भारत",
    statusOnline: "प्रावधान अनुक्रमित",
    statusOffline: "बैकएंड ऑफ़लाइन",
    statusConnecting: "कॉर्पस से जुड़ रहे हैं…",
    endSession: "सत्र समाप्त करें",
    newConsultation: "नया परामर्श",
    consultations: "परामर्श",
    questionsCount: "प्रश्न",
    questionCount: "प्रश्न",
    untitledSession: "नया परामर्श",
    deleteSession: "यह परामर्श हटाएँ",
    deleteAll: "सभी हटाएँ",
    deleteAllConfirm: "सभी सहेजे गए परामर्श हटाएँ?",
    deleteAllYes: "सब हटाएँ",
    deleteAllNo: "रहने दें",
    emptyTitle: "आयुर्वेदिक उत्पाद की सुरक्षा या व्यावसायीकरण के बारे में पूछें।",
    emptySubtitle:
      "हर उत्तर केवल उद्धृत भारतीय क़ानूनों, नियमों और रजिस्ट्री रिकॉर्ड से बनाया गया है — और दिखाता है कि यह कितना सुसमर्थित है। जब कॉर्पस उत्तर नहीं दे सकता, तो वह अनुमान लगाने के बजाय यही बताता है।",
    tryAsking: "यह पूछ कर देखें",
    placeholderAsk: "जैसे: क्या प्रथम अनुसूची ग्रंथ के शास्त्रीय चूर्ण को पेटेंट कराया जा सकता है?",
    placeholderCompare: "जैसे: शास्त्रीय सामग्री लेकिन अपने अनुपात वाला हर्बल सिरप",
    placeholderClarify: "अपना उत्तर लिखें…",
    hintEnter: "पूछने के लिए Enter · नई लाइन के लिए Shift + Enter",
    hintCompare: "उत्पाद का वर्णन करें — देखें हर श्रेणी इसे कैसे मानती है",
    infoNotAdvice: "जानकारी, कानूनी सलाह नहीं",
    sendAsk: "पूछें",
    sendCompare: "तुलना करें",
    sendLoading: "जांच जारी…",
    stop: "रोकें",
    micTooltip: "आवाज़ इनपुट",
    micLangTooltip: "आवाज़ इनपुट की भाषा",
    replyingTo: "इसका उत्तर दें",
    sessionCount: "इस सत्र में",
    couldNotComplete: "पूरा नहीं हो सका",
    dismiss: "खारिज करें",
    classifyingStage: "वर्गीकरण, प्रावधान प्राप्त करना, उद्धरण सत्यापन…",
    comparingStage: "प्रावधान प्राप्त करना, हर श्रेणी की तुलना…",
    menu: "मेनू",
  },
};
