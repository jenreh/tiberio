import { withMermaid } from "vitepress-plugin-mermaid";

export default withMermaid({
  title: "pantau-alexa",
  description:
    "Alexa Smart Home Skill backend — voice-control your TV, blinds & heating from your own server.",
  base: "/",
  lang: "en-US",

  themeConfig: {
    siteTitle: "pantau-alexa",

    nav: [
      { text: "Guide", link: "/guide/", activeMatch: "/guide/" },
      { text: "Architecture", link: "/architecture/", activeMatch: "/architecture/" },
      { text: "Modules", link: "/modules/domain", activeMatch: "/modules/" },
      { text: "Development", link: "/development/", activeMatch: "/development/" },
    ],

    sidebar: {
      "/guide/": [
        {
          text: "Guide",
          items: [
            { text: "What is pantau-alexa?", link: "/guide/" },
            { text: "Getting Started", link: "/guide/getting-started" },
            { text: "Configuration Reference", link: "/guide/configuration" },
          ],
        },
      ],

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
      { icon: "github", link: "https://github.com/example/pantau-alexa" },
    ],

    footer: {
      message: "pantau-alexa — self-hosted Alexa Smart Home backend",
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
