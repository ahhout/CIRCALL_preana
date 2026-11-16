# Apptainer container

Run the commands below from the repository root. For normal local execution use
[the README commands](../README.md#run).

The optional Apptainer image runs all four layers with the existing launcher and
Linux Conda lock. Install Apptainer inside WSL2 Ubuntu or Linux using the
[official installation guide](https://apptainer.org/docs/admin/1.5/installation.html#install-ubuntu-packages).
Docker Desktop is not required. Standard-library Python and Git prepare the build;
Arial's four local TTF styles are also required.

Select an explicit schema-2 master with reviewed workbooks under `sources`;
see [configuration](configuration.md). The helper copies selected bytes
unchanged and does not anonymise them. Deidentification of the current clinical
workbooks has produced validated pseudonymised working copies, with remaining
sharing review in the [to-do list](../README.md#to-do). Use synthetic sources for shared images
until that review is complete. A private local image has been built and validated;
no clinical image has been published. The [acceptance record](history/private_image_20261116.md)
identifies its clean code checkpoint and test results.

```bash
umask 077
mkdir -p .maintenance
mkdir -m 700 .maintenance/container_build_next
python3 environments/container/build.py \
  --config configs/pipeline_layers.json \
  --arial-dir /usr/share/fonts/truetype/msttcorefonts \
  --context .maintenance/container_build_next/context \
  --image .maintenance/container_build_next/circall-preana-private.sif \
  --root-mapped-build
chmod 600 .maintenance/container_build_next/circall-preana-private.sif
```

The example creates a fresh owner-only parent and protects the SIF itself.
Each context and image destination must be fresh; existing files are preserved.
Contexts and SIF images are Git-ignored and can contain selected data and fonts.
`--prepare-only` prepares a context without building. On this WSL installation,
Apptainer 1.5.5's subordinate-ID build fails while mounting `binfmt_misc`;
add `--root-mapped-build` to use the tested root-mapped namespace alternative.
This changes build mechanics only, without changing system configuration.

The font directory must contain `Arial.ttf`, `Arial_Bold.ttf`, `Arial_Italic.ttf`
and `Arial_Bold_Italic.ttf`. The build checks all four styles without fallback.
Use fonts covered by the applicable licence for installation and sharing;
see [Microsoft's redistribution guidance](https://learn.microsoft.com/en-us/typography/fonts/font-faq).
The Conda definition and lock are unchanged; Arial is an image-level asset.

The tested private image below exists only in this workspace and is Git-ignored.
For a newly built image, set `pipeline_image` to its path. Run from WSL/Linux;
without pipeline arguments the image performs preflight:

```bash
umask 077
pipeline_image=.maintenance/private_clinical_image_20261116/circall-preana-private.sif
apptainer run --cleanenv --containall "$pipeline_image"
mkdir -p outputs/container
apptainer run --cleanenv --containall \
  --bind "$PWD/outputs/container:/app/outputs" \
  "$pipeline_image" --output-dir outputs/run_next
```

Execution uses your host UID/GID and a read-only image. The output parent must be
writable; each run destination must not exist. Selected workbooks are embedded
under `/app/input/`. `--containall --cleanenv` avoids the default home/current
working-directory mounts and inherited analysis environment. Only the explicit
output directory is shared with the run. The four-layer clinical gates and exit
codes remain unchanged. See [container provenance](audit_guide.md#container-provenance)
for build hashes, validation and limitations.
