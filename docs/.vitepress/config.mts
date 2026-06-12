import { withMermaid } from "vitepress-plugin-mermaid";

// ReadTheDocs serves docs at /en/latest/ (or /en/<version>/); derive base from
// the canonical URL it injects so asset paths resolve correctly.
const rtdCanonical = process.env.READTHEDOCS_CANONICAL_URL;
const base = rtdCanonical ? new URL(rtdCanonical).pathname : "/";

const guideSidebar = [
  {
    text: "Guide",
    items: [
      { text: "What is Tiberio?", link: "/guide/" },
      { text: "Getting Started", link: "/guide/getting-started" },
      { text: "Configuration Reference", link: "/guide/configuration" },
      { text: "CLI Reference", link: "/guide/cli" },
      { text: "Alexa Skill Setup", link: "/skill-setup" },
    ],
  },
];

export default withMermaid({
  title: "Tiberio",
  description:
    "Alexa Smart Home Skill backend — voice-control your TV, blinds & heating from your own server.",
  base,
  lang: "en-US",

  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: `${base}logo.svg` }],
    ["link", { rel: "alternate icon", type: "image/png", href: `${base}logo.png` }],
    ["meta", { name: "theme-color", content: "#4476af" }],
  ],

  themeConfig: {
    siteTitle: "Tiberio",
    logo: "/logo.svg",

    nav: [
      { text: "Guide", link: "/guide/", activeMatch: "/guide/" },
      { text: "Architecture", link: "/architecture/", activeMatch: "/architecture/" },
      { text: "Modules", link: "/modules/domain", activeMatch: "/modules/" },
      { text: "Development", link: "/development/", activeMatch: "/development/" },
    ],

    sidebar: {
      "/guide/": guideSidebar,
      "/skill-setup": guideSidebar,

      "/architecture/": [
        {
          text: "Architecture",
          items: [
            { text: "System Overview", link: "/architecture/" },
            { text: "Hexagonal Architecture", link: "/architecture/hexagonal" },
            { text: "Message Flows", link: "/architecture/message-flows" },
          ],
        },
      ],

      "/modules/": [
        {
          text: "Modules",
          items: [
            { text: "domain/", link: "/modules/domain" },
            { text: "commands/", link: "/modules/commands" },
            { text: "ports/", link: "/modules/ports" },
            { text: "adapters/", link: "/modules/adapters" },
            { text: "interfaces/alexa/", link: "/modules/interfaces-alexa" },
            { text: "interfaces/oauth/", link: "/modules/interfaces-oauth" },
            { text: "composition.py", link: "/modules/composition" },
          ],
        },
      ],

      "/development/": [
        {
          text: "Development",
          items: [
            { text: "Testing & Contributing", link: "/development/" },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: "github", link: "https://github.com/jenreh/tiberio" },
    ],

    footer: {
      message: "Tiberio — self-hosted Alexa Smart Home backend",
      copyright: "Copyright © 2026",
    },

    search: {
      provider: "local",
    },

    outline: {
      level: [2, 3],
      label: "On this page",
    },
  },

  mermaid: {
    // Default theme. In dark mode the plugin applies the "dark" theme automatically.
  },

  markdown: {
    lineNumbers: true,
  },
});
