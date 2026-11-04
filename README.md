# PipeDirection Orbital

A pyRevit tool designed to create a temporary 3D directional guide for create pipes in Autodesk Revit.

The tool generates an orbital guide around a selected pipe endpoint, allowing users to choose the desired direction for a new pipe segment and automatically connect it using an elbow fitting.

## Requirements

- Autodesk Revit
- pyRevit
- An active 3D view

## Features

- Select an existing pipe and choose the endpoint where the new segment will be created.
- Generate a temporary 3D orbital guide with three directional planes:
  - Transverse plane.
  - Longitudinal plane A.
  - Longitudinal plane B.
- Display radial direction lines at 45-degree intervals.
- Use different colors to distinguish the three planes.
- Select a radial line to define the direction of the new pipe.
- Automatically create a new pipe segment using the original pipe's:
  - System type.
  - Pipe type.
  - Reference level.
  - Diameter.
- Automatically create an elbow fitting between the existing pipe and the new segment.
- Remove the temporary orbital geometry after direction selection.

## Usage

1. Open a Revit 3D view.
2. Run **PipeDirection Orbital**.
3. Select an existing pipe.
4. Click near the endpoint where you want to extend the pipe.
5. Select one of the radial lines on the generated orbital guide.
6. The tool creates the new pipe segment and connects it using an elbow fitting.

## Important Notes

- The orbital guide is temporary and is automatically deleted after direction selection.
- Only free pipe endpoints are supported in this version.
- The new pipe is created with a default length of 1000 mm.
- The elbow takeoff distance is set to 100 mm.
- The orbital radius is set to 350 mm.
- Existing pipe connections are not modified.
- The tool requires an active 3D view.

## Example Workflow

1. Select an existing pipe.
2. Choose its free endpoint.
3. Display the 3D orbital guide.
4. Select the desired radial direction.
5. Automatically generate the pipe extension and elbow fitting.

## Demo

The following example demonstrates how to use the 3D orbital guide to select a pipe direction and create a connected pipe segment within a Revit project.
