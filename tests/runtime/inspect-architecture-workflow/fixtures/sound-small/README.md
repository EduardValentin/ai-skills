# sound-small fixture

A small invented invoicing project with a simple, sound structure: business rules import nothing outside their
component, one storage port has one adapter, one composition root wires them, enforcement is recorded for every
component, and `billing` publishes its surface.

`arch check` must report no row and no incomplete entry and exit 0, even with `--strict`. `arch applicable --all` must
run, and nothing the command prints may ask for more structure.
