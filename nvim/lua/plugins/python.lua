return {
  -- Configure Python LSP to use your default virtual environment
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        pyright = {
          settings = {
            python = {
              pythonPath = vim.fn.expand("~/default/bin/python"),
              analysis = {
                autoSearchPaths = true,
                useLibraryCodeForTypes = true,
                diagnosticMode = "workspace",
                typeCheckingMode = "basic",
                diagnosticSeverityOverrides = {
                  reportReturnType = "none",
                  reportArgumentType = "none",
                  reportOptionalSubscript = "none",
                },
              },
            },
          },
        },
      },
    },
  },

  -- Ensure Python language extras are loaded
  { import = "lazyvim.plugins.extras.lang.python" },
}
