// Modern ATS-Compliant Typst CV Template
// Calibrated to University of Oxford Traditional & Harvard 2025 Career Standards
// Designed for Programmatic Agentic Rendering (Decoupling Data from Presentation)
// Author: Mohammad Mahdi Alsalkadi & ZCO-Hunter AI

#let data_path = sys.inputs.at("data_path", default: "/data/documents/filtered_cv_data.json")
#let cv = json(data_path)

#set page(
  paper: "a4",
  margin: (x: 1.4cm, top: 1.1cm, bottom: 1.1cm)
)

#set text(
  font: ("Liberation Sans", "DejaVu Sans", "Arial"),
  size: 9.2pt,
  fill: rgb("#1e293b"),
  lang: "en"
)

#set par(justify: true, leading: 0.50em)

// Header Section (Oxford & Harvard Strict Standard: No Emojis, Clean Bullet Separators)
#align(center)[
  #text(19pt, weight: "bold", fill: rgb("#0f172a"))[#cv.personal.full_name_en] \
  #v(2pt)
  #text(9.5pt, weight: "bold", fill: rgb("#1e40af"))[#cv.target_subtitle] \
  #v(3pt)
  #text(8.5pt, fill: rgb("#334155"))[
    #cv.personal.location_short
    #h(6pt) • #h(6pt) #link("mailto:" + cv.personal.email)[#cv.personal.email]
    #h(6pt) • #h(6pt) #cv.personal.phone_my
    #if "github_url" in cv.personal and cv.personal.github_url != "" [
      #h(6pt) • #h(6pt) #link(cv.personal.github_url)[#cv.personal.github_url.replace("https://", "").replace("http://", "")]
    ]
    #if "linkedin_url" in cv.personal and cv.personal.linkedin_url != "" [
      #h(6pt) • #h(6pt) #link(cv.personal.linkedin_url)[LinkedIn]
    ]
  ]
]

#v(2pt)

// Section Macro (Oxford Uppercase Divider)
#let cv_section(title) = {
  v(5pt)
  text(9.8pt, weight: "bold", fill: rgb("#0f172a"))[#upper(title)]
  v(-3pt)
  line(length: 100%, stroke: 0.75pt + rgb("#cbd5e1"))
  v(2.5pt)
}

// Target Objective / Focus Statement (Optional, Target-Specific)
#if "objective_statement" in cv and cv.objective_statement != "" [
  #block(
    fill: rgb("#f8fafc"),
    stroke: (left: 2.5pt + rgb("#2563eb")),
    inset: (x: 8pt, y: 4.5pt),
    radius: (right: 3pt),
    width: 100%
  )[
    #text(8.4pt, fill: rgb("#334155"))[
      *Target Alignment:* #cv.objective_statement
    ]
  ]
]

// 1. Education Section (Placed First for Current Undergraduates)
#cv_section("Education & Academic Honours")
#grid(
  columns: (1fr, auto),
  align: (left, right),
  [
    *#cv.education.institution* \
    #text(8.8pt, fill: rgb("#334155"))[
      #cv.education.degree --- #cv.education.faculty
    ]
  ],
  [
    #text(8.5pt, fill: rgb("#475569"))[*#cv.education.academic_year* (Expected: #cv.education.graduation_expected)] \
    #text(8.8pt, weight: "bold", fill: rgb("#15803d"))[CGPA: #cv.education.cgpa]
  ]
)
#v(1pt)
#text(8.2pt, fill: rgb("#475569"))[
  *Relevant Coursework:* #cv.education.core_coursework_str \
  *Language Proficiency:* English (#cv.education.english_proficiency) | Arabic (Native Language)
]

// 2. Technical Projects & Systems Development (CAR / Google XYZ Evidence Bullets)
#cv_section("Technical Projects & Systems Development")
#for prj in cv.projects [
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [*#prj.title* #h(4pt) #text(8pt, fill: rgb("#1d4ed8"), style: "italic")[| #prj.role]],
    [#text(8.2pt, fill: rgb("#64748b"))[#prj.period]]
  )
  #v(-2pt)
  #text(7.6pt, fill: rgb("#475569"))[
    *Technologies:* #prj.technologies_str
  ]
  #v(1pt)
  #for bp in prj.bullet_points [
    #list(
      marker: [•],
      body-indent: 4pt,
      tight: true,
      text(8.3pt, fill: rgb("#334155"))[#bp]
    )
  ]
  #v(1.5pt)
]

// 3. Leadership, Community & Field Activities
#cv_section("Leadership, Community & Field Activities")
#for exp in cv.experience [
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [*#exp.organization* #h(4pt) #text(8pt, fill: rgb("#475569"), style: "italic")[| #exp.role]],
    [#text(8.2pt, fill: rgb("#64748b"))[#exp.period]]
  )
  #v(0.5pt)
  #for det in exp.details [
    #list(
      marker: [•],
      body-indent: 4pt,
      tight: true,
      text(8.3pt, fill: rgb("#334155"))[#det]
    )
  ]
  #v(1.5pt)
]

// 4. Skills & Interests (Harvard 4-Category System: Technical, ML/AI, Languages, Interests)
#cv_section("Skills & Interests")
#grid(
  columns: (115pt, 1fr),
  row-gutter: 2.8pt,
  [*Programming Languages:*], [#cv.skills.programming_str],
  [*Machine Learning & AI:*], [#cv.skills.ml_str],
  [*Developer Tools:*], [#cv.skills.tools_str],
  [*Languages:*], [#cv.skills.languages_str],
  ..if "field_str" in cv.skills and cv.skills.field_str != "" {
    ([*Interests & Fieldwork:*], [#cv.skills.field_str])
  } else { () }
)
