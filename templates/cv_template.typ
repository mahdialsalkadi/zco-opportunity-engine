// Modern ATS-Compliant Typst CV Template
// Designed for Programmatic Agentic Rendering (Decoupling Data from Presentation)
// Author: Mohammad Mahdi Alsalkadi & Antigravity AI

#let data_path = sys.inputs.at("data_path", default: "/data/documents/filtered_cv_data.json")
#let cv = json(data_path)

#set page(
  paper: "a4",
  margin: (x: 1.4cm, top: 1.2cm, bottom: 1.2cm)
)

#set text(
  font: ("Liberation Sans", "DejaVu Sans", "Arial"),
  size: 9.2pt,
  fill: rgb("#1e293b"),
  lang: "en"
)

#set par(justify: true, leading: 0.52em)

// Header Section
#align(center)[
  #text(18pt, weight: "bold", fill: rgb("#0f172a"))[#cv.personal.full_name_en] \
  #v(2pt)
  #text(10pt, weight: "bold", fill: rgb("#1d4ed8"))[#cv.target_subtitle] \
  #v(4pt)
  #text(8.5pt, fill: rgb("#475569"))[
    📍 #cv.personal.location_short
    #h(6pt) • #h(6pt) 📧 #link("mailto:" + cv.personal.email)[#cv.personal.email]
    #h(6pt) • #h(6pt) 📱 #cv.personal.phone_my
    #if "github_url" in cv.personal and cv.personal.github_url != "" [
      #h(6pt) • #h(6pt) 🌐 #link(cv.personal.github_url)[github.com/mahdialsalkadi]
    ]
    #if "linkedin_url" in cv.personal and cv.personal.linkedin_url != "" [
      #h(6pt) • #h(6pt) 💼 #link(cv.personal.linkedin_url)[LinkedIn]
    ]
  ]
]

#v(4pt)

// Section Macro
#let cv_section(title) = {
  v(5pt)
  text(10pt, weight: "bold", fill: rgb("#0f172a"))[#upper(title)]
  v(-3pt)
  line(length: 100%, stroke: 0.75pt + rgb("#cbd5e1"))
  v(3pt)
}

// Target Objective / Focus Box (Only if specified)
#if "objective_statement" in cv and cv.objective_statement != "" [
  #block(
    fill: rgb("#f8fafc"),
    stroke: (left: 2.5pt + rgb("#2563eb")),
    inset: (x: 8pt, y: 5pt),
    radius: (right: 3pt),
    width: 100%
  )[
    #text(8.5pt, fill: rgb("#334155"))[
      *Target Alignment:* #cv.objective_statement
    ]
  ]
]

// Education Section
#cv_section("Education & Academic Foundation")
#grid(
  columns: (1fr, auto),
  align: (left, right),
  [
    *#cv.education.institution* \
    #text(8.8pt, fill: rgb("#475569"))[
      #cv.education.degree --- #cv.education.faculty
    ]
  ],
  [
    #text(8.5pt, fill: rgb("#64748b"))[*#cv.education.academic_year* (Graduation: #cv.education.graduation_expected)] \
    #text(8.8pt, weight: "bold", fill: rgb("#166534"))[CGPA: #cv.education.cgpa]
  ]
)
#v(1pt)
#text(8.2pt, fill: rgb("#475569"))[
  *Core Coursework:* #cv.education.core_coursework_str \
  *English Language:* #cv.education.english_proficiency
]

// Applied Projects Section (Selected & Filtered by Agent)
#cv_section("Technical Projects & Systems Development")
#for prj in cv.projects [
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [*#prj.title* #h(4pt) #text(8pt, fill: rgb("#2563eb"), style: "italic")[| #prj.role]],
    [#text(8.2pt, fill: rgb("#64748b"))[#prj.period]]
  )
  #v(-2pt)
  #text(7.5pt, fill: rgb("#475569"))[
    *Tech:* #prj.technologies_str
  ]
  #v(1pt)
  #for bp in prj.bullet_points [
    #list(
      marker: [•],
      body-indent: 4pt,
      tight: true,
      text(8.4pt, fill: rgb("#334155"))[#bp]
    )
  ]
  #v(2pt)
]

// Relevant Experience & Field Readiness
#cv_section("Leadership, Community & Field Readiness")
#for exp in cv.experience [
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [*#exp.organization* #h(4pt) #text(8pt, fill: rgb("#475569"), style: "italic")[| #exp.role]],
    [#text(8.2pt, fill: rgb("#64748b"))[#exp.period]]
  )
  #v(1pt)
  #for det in exp.details [
    #list(
      marker: [•],
      body-indent: 4pt,
      tight: true,
      text(8.4pt, fill: rgb("#334155"))[#det]
    )
  ]
  #v(2pt)
]

// Skills Section (Prioritized by Opportunity Requirements)
#cv_section("Technical & Practical Competencies")
#grid(
  columns: (115pt, 1fr),
  row-gutter: 3pt,
  [*Programming Languages:*], [#cv.skills.programming_str],
  [*Machine Learning & AI:*], [#cv.skills.ml_str],
  [*Developer Tools:*], [#cv.skills.tools_str],
  [*Languages:*], [#cv.skills.languages_str],
  ..if "field_str" in cv.skills and cv.skills.field_str != "" {
    ([*Environmental & Field:*], [#cv.skills.field_str])
  } else { () }
)
