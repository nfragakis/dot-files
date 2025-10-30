return {
  -- Configure Python LSP to use your default virtual environment
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        -- Disable ruff LSP server
        ruff = {
          enabled = false,
        },
        pyright = {
          settings = {
            python = {
              pythonPath = vim.fn.expand("~/.local/share/mise/installs/python/3.13.9/bin/python"),
              analysis = {
                autoSearchPaths = true,
                useLibraryCodeForTypes = true,
                diagnosticMode = "workspace",
                typeCheckingMode = "basic",
                diagnosticSeverityOverrides = {
                  reportReturnType = "none",
                  reportArgumentType = "none",
                  reportOptionalSubscript = "none",
                  reportOptionalMemberAccess = "none",
                  reportAttributeAccessIssue = "none",
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
