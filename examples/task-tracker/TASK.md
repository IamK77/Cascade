# Task Tracker

Build a command-line task tracker for small teams.

## What it does

A team lead creates projects, adds tasks to projects, assigns tasks to people, and tracks progress. Team members check what's assigned to them and mark things done.

## Features

- Projects have a name, description, and status (active/archived)
- Tasks belong to a project and have a title, description, priority (low/medium/high/urgent), status (todo/in-progress/done/blocked), and optional assignee
- Tasks can depend on other tasks — a task can't move to in-progress if its dependencies aren't done
- Comments on tasks — anyone can add timestamped comments
- A dashboard view: show all projects, how many tasks in each status, who's overloaded (>5 active tasks)
- Filter and search: by assignee, by priority, by status, across projects
- Export a project summary to markdown

## How people use it

```
tracker project create "Website Redesign" --description "Q3 redesign"
tracker task add "Website Redesign" "Design mockups" --priority high --assign alice
tracker task add "Website Redesign" "Implement header" --priority medium --deps "Design mockups"
tracker task update "Design mockups" --status done
tracker task list --assignee alice --status todo
tracker task comment "Implement header" "Waiting on brand colors from marketing"
tracker dashboard
tracker export "Website Redesign" --format markdown
```

## Constraints

- Python, no external dependencies beyond the standard library
- Data stored as JSON files in a `.tracker/` directory
- Must handle concurrent access safely (file locking)
- All commands must have `--help`
- Include tests for the core logic

## Use `/cascade` to build this.
