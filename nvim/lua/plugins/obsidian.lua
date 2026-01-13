return {
  "obsidian-nvim/obsidian.nvim",
  version = "*",
  lazy = true,
  ft = "markdown",
  event = {
    "BufReadPre " .. vim.fn.expand("~") .. "/Notes/personal-os/**.md",
    "BufNewFile " .. vim.fn.expand("~") .. "/Notes/personal-os/**.md",
  },
  dependencies = {
    "nvim-lua/plenary.nvim",
    "hrsh7th/nvim-cmp",
    "nvim-telescope/telescope.nvim",
  },
  opts = {
    workspaces = {
      {
        name = "personal-os",
        path = "~/Notes/personal-os",
      },
    },

    daily_notes = {
      folder = "Daily Notes",
      date_format = "%Y-%m-%d",
      template = "Templates/Daily Template.md",
    },

    templates = {
      folder = "Templates",
      date_format = "%Y-%m-%d",
      time_format = "%H:%M",
      substitutions = {
        yesterday = function()
          return os.date("%Y-%m-%d", os.time() - 86400)
        end,
        tomorrow = function()
          return os.date("%Y-%m-%d", os.time() + 86400)
        end,
      },
    },

    completion = {
      nvim_cmp = false,
      min_chars = 2,
    },

    new_notes_location = "current_dir",

    note_id_func = function(title)
      local suffix = ""
      if title ~= nil then
        suffix = title:gsub(" ", "-"):gsub("[^A-Za-z0-9-]", ""):lower()
      else
        suffix = tostring(os.time())
      end
      return suffix
    end,

    note_frontmatter_func = function(note)
      local out = {
        date = os.date("%Y-%m-%d"),
        tags = note.tags or {},
      }
      if note.metadata ~= nil and not vim.tbl_isempty(note.metadata) then
        for k, v in pairs(note.metadata) do
          out[k] = v
        end
      end
      return out
    end,

    wiki_link_func = function(opts)
      if opts.id == nil then
        return string.format("[[%s]]", opts.label)
      elseif opts.label ~= opts.id then
        return string.format("[[%s|%s]]", opts.id, opts.label)
      else
        return string.format("[[%s]]", opts.id)
      end
    end,

    ui = { enable = false },
    statusline = { enabled = false },
    footer = { enabled = false },
    checkbox = { enabled = false },
    callbacks = {},

    follow_url_func = function(url)
      vim.fn.jobstart({ "xdg-open", url })
    end,

    attachments = {
      img_folder = "Assets/images",
    },

    picker = {
      name = "telescope.nvim",
      mappings = {
        new = "<C-x>",
        insert_link = "<C-l>",
      },
    },
  },
}
