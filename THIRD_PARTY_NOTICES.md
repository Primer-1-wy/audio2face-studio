# Third-party notices

## NVIDIA Audio2Face-3D

Licensed by NVIDIA Corporation under the NVIDIA Open Model License.

Model: https://huggingface.co/nvidia/Audio2Face-3D-v3.0

Revision: `b74132732fd9a9d29b237bec193ded64c9745e91`.

The supplied inference package contains Claire neutral geometry and motion results. Browser derivatives retain the original topology and frame rate; motion is quantized for distribution as documented in the README. The Open Model License is included at `docs/licenses/NVIDIA_OPEN_MODEL_LICENSE.pdf`. The inference examples were provided by the project owner. No network weights are included in this repository.

## NVIDIA Maya-ACE

Copyright (c) 2024 NVIDIA CORPORATION. All rights reserved.

Source: https://github.com/NVIDIA/Maya-ACE/tree/main/sample_project/maya_geom

The v3 Claire Maya scene was parsed as geometry data only, not executed. Face triangulation, UVs, eyes and dentures are derived from that scene. The supplied reference file SHA-256 is `6320bc3c07b8ab981a0f7deda3a555cc9347bfc56e1ac7461133a55a3b5046c0`. MIT license: `docs/licenses/MAYA_LICENSE.txt`.

## NVIDIA Claire lookdev sample

Source: https://omniverse-content-production.s3.us-west-2.amazonaws.com/Samples/Examples/2023_1/Rendering/Claire/

Copyright NVIDIA Corporation. Claire textures have been converted from EXR to PNG, resized to at most 2048 × 2048 and adapted to the v3 UV layout. They retain NVIDIA's applicable content terms and are provided as part of this demonstration, not as an independently licensed stock-asset library. See NVIDIA's [Omniverse license agreement](https://docs.omniverse.nvidia.com/guide-kit-cae/latest/common/NVIDIA_Omniverse_License_Agreement_2022-2023.html). This preview is not the original Omniverse renderer or official lookdev result.

## Three.js

Three.js 0.180.0, copyright the Three.js authors, MIT license. The runtime and license are included under `docs/vendor/three/`; an additional license copy is under `docs/licenses/THREE_LICENSE.txt`.

## Other local tools

`local/` contains integration code and references to NVIDIA SDKs, NVIDIA training code and official examples. Their separately downloaded dependencies retain their upstream licenses; third-party SDK source and model weights are not bundled here. User interface code does not grant rights to third-party characters, textures, input audio or model assets.
