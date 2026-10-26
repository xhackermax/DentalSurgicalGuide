# DSG 9.22.16 · Índice del código

> Generado con AST; no ejecuta ni importa el addon. No editar a mano.

Archivos Python productivos: **170**. SHA-256 del conjunto de fuentes: `d97b89f45db6273a21b415b489dad81cfd2de0eff1820d71550a2e0862c2289d`.

Incluye clases, funciones, métodos y definiciones anidadas. Los enlaces abren el archivo; la columna Línea indica la ubicación exacta. Los números cambian al editar el código.

La dependencia Blender indica imports directos, incluso diferidos; su ausencia no demuestra que un módulo sea puro. Los fragmentos comparten el namespace de su anfitrión.

Regenerar: `python dsg/tools/gen_index.py dsg --write`. Comprobar vigencia: `python dsg/tools/gen_index.py dsg --check`.

## [__init__.py](../__init__.py)

584 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 44 | `_blender_api` |  |
| 97 | `__getattr__` |  |
| 103 | `_loaded` | Return an already loaded child module or ``None`` (never imports). |
| 114 | `_addon_dir` |  |
| 118 | `_ensure_package_path` | Guarantee that Blender treats ``dsg`` as a real package. |
| 139 | `_validate_installation` | Fail early with a precise message if Blender kept a partial install. |
| 175 | `_import_submodule` | Load a DSG submodule from its exact file path. |
| 232 | `_load_modules` | Load DSG modules once, in dependency order, after ``dsg`` is ready. |
| 320 | `_quiesce_legacy_handlers` | Remove callbacks left by older DSG versions before RNA registration. |
| 362 | `_configure_panels` |  |
| 400 | `_normal_data_available` |  |
| 410 | `_deferred_initialize` | Initialize scene/object handoff only after _RestrictData is gone. |
| 468 | `_register_deferred_initializer` |  |
| 475 | `_unregister_deferred_initializer` |  |
| 480 | `register` |  |
| 551 | `unregister` |  |

## [_alignment_parts/00_alignment_core.py](../_alignment_parts/00_alignment_core.py)

1319 líneas · imports Blender: bpy, bpy_extras, mathutils · namespace de `alignment_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 175 | `_is_spanish` |  |
| 180 | `_t` |  |
| 185 | `_zone_label` |  |
| 191 | `_report` |  |
| 195 | `_set_role` |  |
| 202 | `_object_role` |  |
| 206 | `_latest_role_object` |  |
| 210 | `_is_dicom_or_alignment_helper` |  |
| 228 | `_set_guide_entry_solid_view` |  |
| 257 | `_set_principled_value` |  |
| 270 | `_set_alignment_material_preview` | Use Material Preview while reviewing the IOS and FDI overlays. |
| 295 | `ensure_ios_gray_material` | Give the IOS one stable neutral-gray Material Preview appearance. |
| 331 | `_set_dicom_collections_hidden` |  |
| 335 | `_hide_dicom_scene_objects_except` | Hide DICOM volume/MPR helpers while keeping only the generated STL review meshes. |
| 368 | `_clinical_cbct_review_objects` | Legacy visual overlays only. |
| 406 | `_disable_clinical_cbct_review_smoothing` |  |
| 416 | `_prepare_alignment_review_view` | Review IOS against the high-resolution segmented CBCT teeth. |
| 522 | `_isolate_aligned_ios_for_guide` |  |
| 551 | `_is_alignment_candidate` | Any real mesh may be the moving object; roles never restrict alignment. |
| 562 | `_is_valid_reference_mesh` |  |
| 572 | `_latest_alignment_reference` | Find any usable fixed mesh, without forcing a dental-teeth role. |
| 596 | `_auto_detect_models` |  |
| 628 | `_set_active_only` | Make one object visible, selected and active without touching geometry. |
| 650 | `_import_stl_file` | Import one STL with Blender 5.x and retain compatibility with older builds. |
| 694 | `_matrix_to_text` |  |
| 698 | `_matrix_from_text` |  |
| 710 | `_ensure_object_mode` |  |
| 716 | `_alignment_composite_dental_bvh` | Build an in-memory dental BVH without creating a third Blender object. |
| 759 | `_validate_models` |  |
| 771 | `_assign_from_selection` |  |
| 782 | `_landmark_attr` |  |
| 786 | `_get_local_landmarks` |  |
| 791 | `_set_local_landmark` |  |
| 795 | `_clear_landmark_values` |  |
| 820 | `_world_landmarks` |  |
| 824 | `_landmark_collection` |  |
| 832 | `_clear_markers` |  |
| 847 | `_set_markers_hidden` |  |
| 855 | `_marker_size` |  |
| 862 | `_create_marker` |  |
| 880 | `_rebuild_markers` |  |
| 895 | `_to_world` |  |
| 901 | `_to_world_normals` |  |
| 908 | class `_MeshGraph` | Evaluated mesh data read once and reused by all three automatic areas. |
| 913 | `_MeshGraph.__init__` |  |
| 920 | `_MeshGraph.nearest_vertex` |  |
| 927 | `_MeshGraph.vertices_inside_radius` |  |
| 943 | `_immediate_alignment_teeth` | Return the original segmented teeth represented by an immediate target. |
| 978 | `_registration_mesh_source` | A DSG display modifier must never change the clinical ICP reference. |
| 990 | `_mesh_graph_from_objects` | Concatenate several mesh objects into one in-memory world-space graph. |
| 1045 | `_extract_world_mesh_graph` | Read evaluated vertices, normals and edge topology with foreach_get. |
| 1103 | `_voxel_downsample` |  |
| 1123 | class `_NearestIndex` | Vectorized SciPy queries when available, compact Blender fallback otherwise. |
| 1126 | `_NearestIndex.__init__` |  |
| 1137 | `_NearestIndex.query` |  |
| 1159 | `_best_fit` |  |
| 1225 | `_rotation_matrix_from_vector` | Rodrigues rotation from a small axis-angle vector in radians. |
| 1237 | `_point_to_plane_huber_transform` | Return one small robust point-to-plane rigid increment. |

## [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py)

1391 líneas · imports Blender: ninguno directo · namespace de `alignment_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `_apply_points` |  |
| 11 | `_apply_normals` |  |
| 19 | `_rotation_degrees` |  |
| 26 | `_trimmed_correspondences` |  |
| 45 | `_triangle_metrics` |  |
| 57 | `_validate_single_landmark_triangle` |  |
| 74 | `_validate_landmark_geometry` |  |
| 119 | class `DICP_Props` |  |
| 179 | class `DICP_OT_ImportIOSSTL` | `dicp.import_ios_stl` · Import intraoral STL |
| 188 | `DICP_OT_ImportIOSSTL.execute` |  |
| 249 | class `DICP_OT_AutoDetect` | `dicp.auto_detect` · Detect models |
| 255 | `DICP_OT_AutoDetect.execute` |  |
| 276 | class `DICP_OT_UseSelection` | `dicp.use_selection` · Usar 2 seleccionados |
| 282 | `DICP_OT_UseSelection.execute` |  |
| 305 | class `DICP_OT_PickLandmarks` | `dicp.pick_landmarks` · Marcar zonas |
| 325 | `DICP_OT_PickLandmarks._save_object_state` |  |
| 332 | `DICP_OT_PickLandmarks._ensure_in_view_layer` | Make an ICP participant addressable by hide_set/select/raycast. |
| 353 | `DICP_OT_PickLandmarks._restore_scene_state` |  |
| 377 | `DICP_OT_PickLandmarks._focus` |  |
| 405 | `DICP_OT_PickLandmarks._set_status` |  |
| 424 | `DICP_OT_PickLandmarks._raycast` |  |
| 456 | `DICP_OT_PickLandmarks._cancel` |  |
| 464 | `DICP_OT_PickLandmarks.invoke` |  |
| 548 | `DICP_OT_PickLandmarks.modal` |  |
| 673 | `_ensure_scipy_kdtree` | Load SciPy from DSG's private runtime if the module import missed it. |
| 687 | `_crop_near_seeds` |  |
| 701 | `_three_point_matches` |  |
| 710 | `three_point_icp` | Return (transform 4x4, iterations) aligning source onto target. |
| 737 | `three_point_metrics` | RMS, p95, overlap and per-zone details after alignment. |
| 764 | class `DICP_OT_RunAlignment` | `dicp.run_alignment` · Alinear modelos |
| 770 | `DICP_OT_RunAlignment.execute` |  |
| 896 | class `DICP_OT_ReviewAlignment` | `dicp.review_alignment` · Revisar |
| 902 | `DICP_OT_ReviewAlignment.execute` |  |
| 915 | class `DICP_OT_SendToDSG` | `dicp.send_to_dsg` · Siguiente |
| 921 | `DICP_OT_SendToDSG.execute` |  |
| 966 | class `DICP_OT_RestoreSource` | `dicp.restore_source` · Restaurar posición |
| 972 | `DICP_OT_RestoreSource.execute` |  |
| 999 | class `DICP_OT_ClearLandmarks` | `dicp.clear_landmarks` · Redibujar puntos |
| 1005 | `DICP_OT_ClearLandmarks.execute` |  |
| 1020 | class `DICP_OT_BackToAlignment` | `dicp.back_to_alignment` · Deshacer última acción |
| 1026 | `DICP_OT_BackToAlignment.execute` |  |
| 1050 | class `DICP_OT_Reset` | `dicp.reset` · Back to Alignment Start |
| 1056 | `DICP_OT_Reset.invoke` |  |
| 1059 | `DICP_OT_Reset.execute` |  |
| 1200 | `_draw_reset_flow_panel` | Navigation/restart controls live in the shared DSG control panel. |
| 1205 | class `DICP_PT_Main` | `DICP_PT_main` · Alignment |
| 1214 | `DICP_PT_Main.poll` |  |
| 1220 | `DICP_PT_Main.draw` |  |
| 1268 | `_draw_tooth_analyzer_section` | Show the CBCT dentition handoff; IOS is no longer re-segmented for FDI. |
| 1303 | `_alignment_unregister_class_object` |  |
| 1313 | `_alignment_unregister_stale_classes` | Remove RNA classes left by a previous DSG/alignment installation. |
| 1334 | `_alignment_remove_stale_scene_pointer` |  |
| 1347 | `register` |  |
| 1374 | `unregister` |  |

## [_dicom_parts/00_constants_runtime_dependencies.py](../_dicom_parts/00_constants_runtime_dependencies.py)

1026 líneas · imports Blender: bpy · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 298 | class `VolumeRuntime` | Large data that should not be stored in Blender RNA properties. |
| 399 | `VolumeRuntime.is_loaded` |  |
| 402 | `VolumeRuntime.source_exists` |  |
| 405 | `VolumeRuntime.reset` | Release the volume and all metadata references. |
| 503 | `_dw_spanish` |  |
| 508 | `_dw_t` |  |
| 513 | `_dw_status` |  |
| 540 | `_dw_report` |  |
| 544 | `_set_suite_role` |  |
| 551 | `_suite_role` |  |
| 558 | `_dicom_vendor_dir` | Return a writable DICOM runtime directory without assuming its path is free. |
| 595 | `_dicom_wheel_tags` |  |
| 608 | `_dicom_runtime_abi_compatible` |  |
| 621 | `_legacy_dicom_candidates` |  |
| 637 | `_activate_dicom_vendor` |  |
| 672 | `load_module` |  |
| 703 | `load_full_pydicom` | Return the real third-party pydicom package, never DSG's mini fallback. |
| 708 | `full_pydicom_available` |  |
| 712 | `_dataset_transfer_syntax_uid` |  |
| 720 | `_transfer_syntax_requires_decoder` |  |
| 727 | `dicom_runtime_status` |  |
| 765 | `dicom_transfer_syntax_support` | Return whether DSG can *attempt* this DICOM transfer syntax. |
| 804 | `dicom_standard_cbct_ready` | True when the runtime covers the normal CT/CBCT pixel syntax families. |
| 814 | `dicom_preflight_report` |  |
| 832 | `dicom_install_state` |  |
| 837 | `_set_dicom_install_state` |  |
| 842 | `_install_dicom_runtime_worker` | Prepare the full DICOM reader from a compatible runtime or local wheelhouse only. |
| 897 | `start_dicom_runtime_install` | Compatibility entry point: install on Blender's main Python thread. |
| 911 | `load_numpy` |  |
| 915 | `load_pydicom` | Return full pydicom when already bundled by Blender, else DSG's reader. |
| 932 | `load_openvdb` | Return Blender's OpenVDB Python module when available. |
| 937 | `_load_scientific_module` | Load an optional scientific module from Blender or DSG 9.10 runtime. |
| 953 | `load_scipy_ndimage` |  |
| 957 | `load_scipy_spatial` |  |
| 961 | `load_skimage_measure` |  |
| 965 | `load_skimage_filters` |  |
| 969 | `load_skimage_segmentation` |  |
| 973 | `load_vtk` | Optional VTK accelerator used for compact CBCT Flying Edges meshing. |
| 982 | `load_simpleitk` | Optional ITK-backed dental segmentation engine. |
| 997 | `dependency_summary` |  |

## [_dicom_parts/01_utils_dicom_io.py](../_dicom_parts/01_utils_dicom_io.py)

1433 líneas · imports Blender: bpy · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `clamp` |  |
| 11 | `safe_float` |  |
| 20 | `safe_int` |  |
| 27 | `as_tuple3` |  |
| 37 | `force_ui_redraw` |  |
| 46 | `progress_begin` |  |
| 53 | `progress_update` |  |
| 61 | `progress_end` |  |
| 87 | `_cached_header` | Read/cache metadata without forcing enhanced per-frame sequences on the UI thread. |
| 128 | class `SourceProbe` | Lightweight information shown before decoding the pixel volume. |
| 156 | `SourceProbe.dimensions_text` |  |
| 160 | `SourceProbe.spacing_text` |  |
| 203 | `_first_item` |  |
| 213 | `_sequence_item` |  |
| 223 | `_nested_first` |  |
| 232 | `read_header` | Read metadata without Pixel Data; enhanced per-frame data is opt-in. |
| 267 | `_pixel_measures` |  |
| 280 | `pixel_spacing` |  |
| 298 | `slice_spacing` |  |
| 309 | `image_orientation` |  |
| 332 | `image_position` |  |
| 343 | `rescale_values` |  |
| 365 | `_orientation_matrix` |  |
| 374 | `_orientation_matrix.normalized` |  |
| 385 | `_position_projection` |  |
| 393 | `_discover_series` | Find files belonging to the same classic DICOM series. |
| 409 | `_discover_series.consider` |  |
| 470 | `_discover_series.sort_key` |  |
| 485 | `_infer_multiframe_z_spacing` |  |
| 508 | `_multiframe_slice_order` | Return (order, positions) so frames ascend along the slice normal. |
| 534 | `_warn_if_orientation_missing` |  |
| 550 | `_infer_classic_z_spacing` |  |
| 566 | `_estimate_memory_mb` |  |
| 571 | `_valid_image_dimensions` |  |
| 579 | `_sort_recovered_series_items` | Sort recovered classic-series slices across arbitrary subdirectories. |
| 586 | `_sort_recovered_series_items.sort_key` |  |
| 601 | `_warn_if_slices_without_position` |  |
| 610 | `_bounded_recursive_files` | Return files below *root* without trusting filename extensions. |
| 642 | `_recovery_search_roots` | Choose bounded study-tree roots for recovery of a non-image DICOM. |
| 677 | `_dicomdir_referenced_paths` | Resolve ReferencedFileID entries when the selected object is DICOMDIR. |
| 718 | `_candidate_series_near_selection` | Discover image-bearing DICOM series around a non-image selection. |
| 742 | `_candidate_series_near_selection.add_path` |  |
| 841 | `_recover_image_source` |  |
| 896 | `probe_source` | Inspect a selected DICOM file and determine whether it is multi-frame. |
| 998 | `_decode_pixel_array` | Decode one DICOM image through quiet compatibility fallbacks. |
| 1064 | `_grayscale_frame` |  |
| 1082 | `_load_multiframe` |  |
| 1135 | `_resolve_classic_series_in_worker` | Resolve all slices/geometry for a classic DICOM series off the UI thread. |
| 1171 | `_load_classic_series` |  |
| 1208 | `_sample_density_statistics` |  |
| 1238 | `_prepare_external_pipeline_cache` | Write one mmap-friendly copy while DICOM is already decoding off UI. |
| 1261 | `_decode_volume_payload` | Pure file/NumPy stage. Safe to run outside Blender's UI thread. |
| 1330 | `_commit_volume_payload` | Main-thread stage: publish a decoded payload to DSG's shared runtime. |
| 1341 | `rehydrate_runtime` | Put the CBCT voxels back in memory for a scene that already has them. |
| 1354 | `_publish_volume_payload` |  |
| 1381 | `load_volume` | Synchronous compatibility wrapper. Clinical UI uses the async modal path. |
| 1387 | `write_header_text` | Write a bounded metadata summary without serializing huge frame sequences. |

## [_dicom_parts/02_volume_mpr_scene.py](../_dicom_parts/02_volume_mpr_scene.py)

2054 líneas · imports Blender: bpy, mathutils · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 11 | `_cache_path` |  |
| 29 | `_preview_axis_indices` | Return regular preview indices that always include both endpoints. |
| 46 | `_preview_sampled_shape` |  |
| 55 | `_density_sample` | Sample the same full DICOM grid used by MPR, preserving its endpoints. |
| 86 | `build_vdb_preview` | Write an adaptively decimated full-volume VDB preview. |
| 147 | `_socket` |  |
| 155 | `_volume_material_is_valid` | Return True only for the current persistent clinical GPU preview schema. |
| 184 | `get_or_create_volume_material` | Create one persistent, non-emissive clinical threshold preview shader. |
| 353 | `_density_to_normalized` |  |
| 358 | `update_volume_material` | Update only scalar sockets in the persistent clinical GPU shader. |
| 430 | `create_volume_object` |  |
| 511 | `remove_cached_vdb` |  |
| 529 | class `SliceResult` |  |
| 543 | `density_from_percent` |  |
| 548 | `threshold_values` |  |
| 558 | `_normalize` |  |
| 567 | `_rotation_matrix` |  |
| 587 | `plane_basis` |  |
| 619 | `_base_geometry` |  |
| 654 | `_scaled_axial` |  |
| 663 | `_scaled_coronal` |  |
| 670 | `_scaled_sagittal` |  |
| 677 | `_direct_slice` |  |
| 695 | `_trilinear_sample` | Sample the raw [z,y,x] volume at centered local physical points. |
| 733 | `_trilinear_sample.voxel` |  |
| 760 | `get_cbct_density_info` | Public JSON-safe description of the currently loaded CBCT density runtime. |
| 783 | `sample_cbct_density_world` | Sample the existing CBCT runtime at Blender world-space XYZ points. |
| 834 | `_oblique_slice` |  |
| 868 | `normalize_for_display` |  |
| 875 | `reconstruct_slice` | Return an orthogonal or oblique MPR slice and its plane geometry. |
| 942 | `_dicom_display_signs_xyz` | Return the root-local signs for DICOM voxel axes without reflections. |
| 959 | `_collection_in_tree` | Return True when *target* belongs to the current scene collection tree. |
| 976 | `_layer_collection_path` | Return the LayerCollection path leading to *target_collection*. |
| 987 | `ensure_collection_in_view_layer` | Make an existing collection usable from the active Blender ViewLayer. |
| 1040 | `object_in_view_layer` |  |
| 1055 | `ensure_object_in_view_layer` | Repair collection linkage for *obj* before selection/activation. |
| 1088 | `safe_select_object` | Select an object only after guaranteeing active ViewLayer membership. |
| 1124 | `get_collection` |  |
| 1140 | `ensure_linked` |  |
| 1145 | `get_root` |  |
| 1170 | `apply_patient_orientation` | Orient local voxel axes using DICOM direction cosines. |
| 1205 | `_new_or_replace_mesh_object` |  |
| 1228 | `create_bounding_box` |  |
| 1266 | `_get_image` |  |
| 1286 | `_set_image_pixels` | Upload pixels without changing the DICOM row direction. |
| 1313 | `_get_plane_material` |  |
| 1344 | `_build_plane_mesh` | Build a plane around its own origin and place it with matrix_local. |
| 1389 | `_plane_parameters` |  |
| 1398 | `refresh_plane` |  |
| 1437 | `_matrix_basis_signature` | Return a stable signature for an object's user-editable transform. |
| 1443 | `_plane_pose_from_object` | Read the current plane pose in DICOM-root local millimetres. |
| 1482 | `_pose_output_shape` | Choose an MPR resolution from physical size and source voxel spacing. |
| 1495 | `_safe_review_refresh_plane_image` | Reconstruct into a new image datablock, then atomically swap texture. |
| 1584 | `_safe_review_request_realtime_refresh` | Request a safe real-time preview without mutating visible image buffers. |
| 1615 | `_safe_review_request_realtime_refresh._run` |  |
| 1709 | `_safe_review_schedule_image_refresh` | Debounce a safe immutable texture rebuild after modal interaction. |
| 1722 | `_safe_review_schedule_image_refresh._run` |  |
| 1763 | `refresh_plane_image_from_object` | Resample the volume using the plane's actual viewport transform. |
| 1807 | `refresh_plane_images_from_objects` |  |
| 1822 | `update_visibility` |  |
| 1876 | `refresh_planes` |  |
| 1887 | `refresh_volume_material` |  |
| 1928 | `create_viewer_scene` |  |
| 1950 | `set_viewport_material_mode` |  |
| 1963 | `frame_viewer` |  |
| 1990 | `cleanup_scene` |  |
| 2041 | `update_density_labels` |  |

## [_dicom_parts/03_updates_segmentation.py](../_dicom_parts/03_updates_segmentation.py)

2675 líneas · imports Blender: bpy, bpy_extras, mathutils · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `_request` |  |
| 32 | `_run_pending_refresh` |  |
| 75 | `on_threshold_change` | Update the GPU shader immediately; defer expensive MPR pixel rebuilding. |
| 95 | `on_segmentation_threshold_preview_change` | Drive the STL preview with one cheap shader value and mark masks stale. |
| 114 | `on_plane_change` |  |
| 119 | `on_active_plane_change` |  |
| 129 | `on_visibility_change` |  |
| 133 | `on_opacity_change` |  |
| 144 | `on_preview_appearance_change` | Adjust edge width/contrast through scalar sockets only. |
| 156 | `on_orientation_display_change` | Reapply the DICOM root orientation after changing display correction. |
| 164 | `_axis_control_names` | Return the six RNA property names for one MPR plane. |
| 177 | `_axis_control_values` |  |
| 182 | `_volume_extents_xyz_mm` | Return physical DICOM extents in root-local X/Y/Z millimetres. |
| 193 | `_orthonormal_rotation_matrix` | Return the nearest proper 3x3 rotation matrix. |
| 207 | `_mpr_alignment_matrix` | Read the shared anatomical MPR frame stored in the scene. |
| 223 | `_store_mpr_alignment_matrix` |  |
| 228 | `_base_plane_frame` | Return columns [U, V, normal] for an unrotated MPR plane. |
| 237 | `_refresh_all_aligned_planes` | Apply the shared frame and reconstruct all three orthogonal cuts. |
| 255 | `_apply_axis_controls_to_plane` | Apply six sliders to the selected plane in DICOM-local coordinates. |
| 341 | `on_axial_axis_control_change` |  |
| 345 | `on_coronal_axis_control_change` |  |
| 349 | `on_sagittal_axis_control_change` |  |
| 353 | `_prepare_minimal_orthogonal_mpr` | Initialise the review planes in one shared anatomical frame. |
| 398 | `_new_segmentation_state` |  |
| 411 | `get_segmentation_state` |  |
| 422 | `_linear_indices_from_zyx` |  |
| 428 | `_zyx_from_linear` |  |
| 439 | `_seed_array` | Return segmentation seed indices as a flat int64 NumPy array. |
| 465 | `_plane_sampling_points` |  |
| 477 | `_nearest_voxel_indices` |  |
| 495 | `_sample_cropped_mask` |  |
| 514 | `compose_segmentation_overlay` | Blend segmentation, positive seeds, and exclusion seeds over an MPR. |
| 551 | `sync_segmentation_properties` |  |
| 567 | `_segmentation_refreshes_all_mpr_planes` | Refresh the radiographic buffers required by the active review mode. |
| 575 | `_refresh_segmentation_views` |  |
| 589 | `on_segmentation_view_change` |  |
| 609 | `_mouse_hit_active_plane` |  |
| 637 | `clear_segmentation_drawings` |  |
| 652 | `_scaled_roi` |  |
| 665 | `_occupied_bbox_3d` | Return an exact ``(min_zyx, max_zyx_exclusive)`` occupied bounding box. |
| 691 | `_compact_mask` | Crop a 3D mask to its occupied bounding box without coordinate spikes. |
| 715 | `_sample_density_for_automatic_analysis` | Return a robust, decimated sample of the complete CBCT density volume. |
| 740 | `_weighted_histogram_kmeans_thresholds` | Dependency-free 1D histogram clustering used if Multi-Otsu is unavailable. |
| 779 | `_weighted_otsu_threshold` | Dependency-free one-dimensional Otsu threshold on a robust histogram. |
| 807 | `_otsu_split_quality` | Return minority fraction and normalized mean separation for an Otsu split. |
| 822 | `_estimate_metal_cutoff` | Detect a separated extreme radiopaque tail without clipping normal enamel. |
| 851 | `_dense_tissue_valley_threshold` | Estimate the scan-specific valley separating bone from dental tissue. |
| 923 | `_automatic_range_for_structure` | Return the adaptive density interval for the selected DICOM anatomy. |
| 971 | `sync_automatic_range_from_structure` |  |
| 981 | `on_automatic_structure_change` |  |
| 998 | `analyze_automatic_tissue_thresholds` | Learn scanner-adaptive mineral, tooth-support and tooth-seed thresholds. |
| 1145 | `_full_density_mask` | Build one full-resolution mask without materialising a float volume. |
| 1165 | `_filter_dental_seed_mask` | Reject high-density seed components that look like cortex/FOV artefact. |
| 1241 | `_component_filter_from_seeds` | 3D hysteresis: keep support components connected to dense tooth seeds. |
| 1304 | `_clean_automatic_mask` | Small, spacing-aware cleanup without changing anatomical boundaries. |
| 1341 | `_automatic_teeth_mask` | Return a connectivity-constrained dental mask and backend diagnostics. |
| 1419 | `_semantic_engine_root` |  |
| 1423 | `_semantic_source_signature` |  |
| 1436 | `_stable_source_key` | Like the source signature but identical across Blender sessions |
| 1452 | `_semantic_model_kind_for_structure` | Return the primary engine for a requested segmentation structure. |
| 1480 | `_semantic_labels_dir` | Stable per-CBCT folder (the pipeline input cache is renamed on every |
| 1497 | `persist_semantic_labels` | Copy the active labelmap next to the per-source CBCT cache. |
| 1526 | `restore_semantic_labels` | Reload the persisted labelmap for the current CBCT (never infers). |
| 1552 | `_load_semantic_labels_cached` | Query the one active semantic labelmap without triggering inference. |
| 1569 | `get_cached_semantic_cbct_labels` | Return cached labels only; never starts a neural inference (CQS query). |
| 1579 | `_store_semantic_result` | Commit one validated full-size labelmap as the semantic SSOT. |
| 1602 | `predict_semantic_cbct_labels_sync` | Compatibility cache query. DSG 9.10 never runs neural inference on Blender's UI thread. |
| 1619 | `_semantic_classes_for_structure` |  |
| 1635 | `_semantic_mask_for_structure` |  |
| 1645 | `_semantic_compact_mask_for_structure` | Return only the occupied semantic ROI, avoiding a full-FOV boolean copy. |
| 1683 | `_compact_mask_for_classes` | Return a compact native-resolution bool mask for explicit integer classes. |
| 1714 | `_embed_compact_mask` |  |
| 1727 | `_ellipsoid_structure` | Anisotropic structuring element expressed in physical millimetres. |
| 1739 | `_fuse_mandibular_canal_masks` | Conservative canal cleanup for normalized DSG class 55. |
| 1853 | `_mandibular_canal_material` | High-visibility clinical material for the learned IAN canal mask. |
| 1878 | `_filter_mandibular_canal_components` | Remove only tiny isolated class-55 speckles; retain anatomical variants. |
| 1927 | `build_mandibular_canal_surface` | Materialise the IAN canal at native mask resolution. |
| 2048 | `segment_tissue_semantically` |  |
| 2095 | `segment_tissue_automatically` | Create a full-resolution mask with tissue-specific 3D logic. |
| 2205 | `_require_mask` |  |
| 2213 | `_rle_component_analysis` | Label 3D binary components with run-length encoding and union-find. |
| 2233 | `_rle_component_analysis.make_set` |  |
| 2238 | `_rle_component_analysis.find` |  |
| 2244 | `_rle_component_analysis.union` |  |
| 2254 | `_rle_component_analysis.row_runs` |  |
| 2269 | `_rle_component_analysis.union_rows` |  |
| 2309 | `_mask_from_component_roots` |  |
| 2313 | `_mask_from_component_roots.find` |  |
| 2327 | `_component_statistics` | Return physical-shape statistics for run-length connected components. |
| 2331 | `_component_statistics.find` |  |
| 2359 | `_roots_overlapping_mask` | Return component roots whose runs overlap at least one True voxel. |
| 2363 | `_roots_overlapping_mask.find` |  |
| 2376 | `_root_overlap_voxel_counts` | Count overlap voxels for each connected-component root. |
| 2380 | `_root_overlap_voxel_counts.find` |  |
| 2395 | `remove_small_islands` | Remove small 3D components with SciPy when present, RLE otherwise. |
| 2446 | `_window_morphology_axis` |  |
| 2458 | `_binary_box_morphology` |  |
| 2465 | `close_segmentation_gaps` |  |
| 2482 | `fill_segmentation_holes` |  |
| 2498 | `_surface_material` |  |
| 2526 | `_dicom_surface_alpha_from_props` | Return the fixed radiographic alpha used by DSG for generated DICOM STL. |
| 2532 | `_configure_transparent_material` | Make a material really transparent in Blender Solid/Material previews. |
| 2577 | `_iter_dicom_surface_objects` | Yield generated DICOM STL surfaces that may hide the radiographic slice. |
| 2606 | `_apply_dicom_surface_transparency` | Apply the ghost transparency slider to the generated DICOM STL. |
| 2663 | `on_dicom_surface_transparency_change` |  |

## [_dicom_parts/04_hybrid_surface_preview.py](../_dicom_parts/04_hybrid_surface_preview.py)

2889 líneas · imports Blender: ninguno directo · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `_surface_preview_material` | Return one stable opaque material for the disposable solid preview. |
| 43 | `_ensure_surface_preview_object` | Create a persistent object/mesh pair so rebuilding never swaps materials. |
| 95 | `_clear_surface_preview_geometry` |  |
| 123 | `_surface_preview_matches` |  |
| 141 | `_cached_surface_preview_sample` |  |
| 151 | `_set_surface_preview_mesh` | Replace geometry in one persistent mesh datablock on Blender's main thread. |
| 205 | `_sampled_hysteresis_mask` | Connectivity-only hysteresis for the bounded DICOM preview grid. |
| 223 | `_build_surface_preview` | Build a bounded solid preview with the same native engine as final output. |
| 322 | `_surface_preview_timer` |  |
| 344 | `_auto_solid_preview_enabled` | The solid preview is bundled with DSG and has no external engine gate. |
| 349 | `schedule_surface_preview` | Invalidate the old solid and schedule one low-resolution rebuild. |
| 397 | `on_auto_solid_preview_change` | Keep the automatic solid preview permanently enabled. |
| 412 | `on_surface_preview_quality_change` |  |
| 421 | `_save_clinical_view_state` |  |
| 438 | `configure_clinical_preview_view` | Create a clean diagnostic-style viewport without changing user objects. |
| 498 | `restore_clinical_preview_view` |  |
| 529 | `_segmentation_vdb_path` |  |
| 540 | `_write_binary_mask_vdb` |  |
| 571 | `_evaluated_mesh_from_object` |  |
| 584 | `_normalized_density_threshold` |  |
| 593 | `_sample_density_for_surface` | Return density samples and their exact original voxel indices. |
| 652 | `_refine_density_for_surface` | Reduce staircase artefacts without drifting far from the selected threshold. |
| 672 | `_extract_triplanar_contour_clouds` | Extract hidden subpixel contour constraints from all useful MPR slices. |
| 720 | `_extract_triplanar_contour_clouds.add_contours` |  |
| 795 | `_mesh_vertex_normals_numpy` |  |
| 816 | `_sample_axis_spacing_mm` |  |
| 828 | `_vertices_xyz_to_sample_coordinates` | Convert root-local millimetres to fractional sampled-grid coordinates. |
| 844 | `_project_vertices_to_threshold_field` | Project vertices onto the trilinearly interpolated CBCT threshold field. |
| 928 | `_taubin_smooth_vertices` | One low-shrinkage smoothing cycle used only before final reprojection. |
| 938 | `_taubin_smooth_vertices.laplacian` |  |
| 955 | `_refine_vertices_with_triplanar_contours` | Move vertices only along their normals toward agreeing MPR contours. |
| 1066 | `_interpolate_sample_coordinates` | Map fractional sampled-grid coordinates to original voxel indices. |
| 1082 | `_centered_xyz_from_sample_vertices` | Convert marching-cubes (z,y,x) vertices into MPR-local (x,y,z) mm. |
| 1115 | `_marching_cubes_cropped` | Extract the occupied region and return centered XYZ vertices. |
| 1200 | `_threshold_bbox_native` | Locate thresholded anatomy cheaply, then return native inclusive/exclusive bounds. |
| 1238 | `_density_native_slab` | Read and rescale only one native CBCT slab into float32. |
| 1253 | `_native_threshold_cache_key` | Cheap identity for the currently loaded immutable DICOM volume. |
| 1267 | `_load_torch_for_surface_acceleration` | Reuse DSG 9.10's shared numerical runtime without making Torch mandatory. |
| 1282 | `_native_density_fullres_cached` | Return one calibrated float32 native CBCT volume, cached by source. |
| 1311 | `_native_threshold_index_cached` | Build/reuse exact block min/max hierarchy on the native scalar grid. |
| 1343 | `_warm_native_threshold_engine_async` | Warm the native scalar/index cache while the clinician reviews the CBCT. |
| 1363 | `_warm_native_threshold_engine_async._worker` |  |
| 1383 | `_refine_native_slab` | Apply a very small physical-space blur to suppress voxel stairs, not anatomy. |
| 1405 | `_global_voxel_to_centered_xyz` | Convert native global voxel ZYX coordinates to root-local XYZ millimetres. |
| 1419 | `_centered_xyz_to_global_voxel` |  |
| 1432 | `_runtime_density_at_voxel_coordinates` | Trilinearly sample calibrated DICOM density without copying the volume. |
| 1452 | `_project_vertices_to_native_threshold` | Reproject a smoothed HD mesh to the original native DICOM threshold. |
| 1501 | `_weld_triangle_arrays` | Merge coincident slab-boundary vertices and discard degenerate triangles. |
| 1525 | `_native_threshold_voxel_shell_chunked` | Dependency-free native threshold surface for the SIMPLE implant route. |
| 1558 | `_native_threshold_voxel_shell_chunked.grid_id` |  |
| 1561 | `_native_threshold_voxel_shell_chunked.append_faces` |  |
| 1666 | `_marching_cubes_native_chunked` | Extract a native-resolution isosurface in overlapping Z slabs. |
| 1740 | `_new_surface_from_arrays` | Create a large triangle mesh using Blender bulk collection writes. |
| 1805 | `_apply_stl_orientation_correction` | Keep the mesh in the exact same root-local frame as its source volume. |
| 1824 | `_sampled_voxel_volume_mm3` |  |
| 1831 | `_sampled_voxel_volume_mm3._axis_step_mm` |  |
| 1843 | `_apply_small_island_cleanup_to_sampled_values` |  |
| 1865 | `generate_direct_density_surface` | Compatibility entry point for the adaptive DSG DICOM segmentation engine. |
| 1875 | `_axis_voxel_boundaries` | Cell-boundary coordinates for sampled voxel-center indices. |
| 1889 | `_voxel_shell_from_sampled_mask` | Triangulate a sampled binary mask in the exact DICOM voxel frame. |
| 1913 | `_voxel_shell_from_sampled_mask.grid_id` |  |
| 1916 | `_voxel_shell_from_sampled_mask.add_quads` |  |
| 1970 | `_native_voxel_shell_from_mask` | Triangulate the boundary of a binary mask using Blender + NumPy only. |
| 1997 | `generate_segmentation_surface` | Convert the active AI mask to Blender-native surfaces. |
| 2169 | `_prepare_mask_surface_arrays` | Pure numeric native-resolution mask surface for worker use. |
| 2220 | `_prepare_canal_surface_arrays` | Pure numeric canal fusion + native marching cubes for worker use. |
| 2254 | `_simple_arch_material` |  |
| 2271 | `_load_prepared_surface_arrays` |  |
| 2281 | `_remove_object_family` |  |
| 2290 | `build_simple_arch_pair` | Materialize exactly two visible SIMPLE meshes and one hidden alignment target. |
| 2325 | `build_semantic_arch_surface` | Materialize one jaw class as its own Blender mesh. |
| 2408 | class `DICOMWizardProProperties` | Small persistent UI state; the voxel array lives in ``runtime.py``. |

## [_dicom_parts/05_realtime_mpr.py](../_dicom_parts/05_realtime_mpr.py)

248 líneas · imports Blender: bpy · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 4 | `_queue_realtime_transform` |  |
| 23 | `_run_realtime_transform_refresh` |  |
| 90 | `dicom_wizard_pro_depsgraph_update` | Detect direct viewport transforms of the DICOM MPR planes. |
| 124 | `_clear_pending_refresh_state` |  |
| 139 | `dicom_wizard_pro_undo_pre` | Freeze callbacks before Blender swaps the undo memfile/depsgraph. |
| 148 | `_repair_after_undo` | Repair links after the new depsgraph is stable, never inside undo itself. |
| 181 | `dicom_wizard_pro_undo_post` | Resume only after undo completed and defer all material access one tick. |
| 199 | `dicom_wizard_pro_redo_pre` |  |
| 204 | `dicom_wizard_pro_redo_post` |  |
| 208 | `register_undo_handlers` |  |
| 216 | `unregister_undo_handlers` |  |
| 232 | `register_realtime_handler` |  |
| 237 | `unregister_realtime_handler` |  |

## [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py)

3024 líneas · imports Blender: blf, bpy, bpy_extras, gpu, mathutils · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `_fill_probe_properties` |  |
| 32 | `_clear_properties` |  |
| 138 | class `DSG_OT_install_dicom_runtime` | `dsg.install_dicom_runtime` · Preparar Motor DICOM offline |
| 147 | `DSG_OT_install_dicom_runtime.execute` |  |
| 171 | `_auto_detect_ai_device_after_dicom` | Cheap compute detection for the external DSG segmentation runtime. |
| 198 | class `DICOMWIZARDPRO_OT_select_file` | `dicom_wizard_pro.select_file` · Elegir DICOM / DCM |
| 217 | `DICOMWIZARDPRO_OT_select_file.execute` |  |
| 265 | class `DICOMWIZARDPRO_OT_next` | `dicom_wizard_pro.next` · Siguiente |
| 280 | `DICOMWIZARDPRO_OT_next.poll` |  |
| 294 | `DICOMWIZARDPRO_OT_next._worker` |  |
| 296 | `DICOMWIZARDPRO_OT_next._worker.cb` |  |
| 315 | `DICOMWIZARDPRO_OT_next._finish_modal` |  |
| 324 | `DICOMWIZARDPRO_OT_next.execute` |  |
| 359 | `DICOMWIZARDPRO_OT_next.modal` |  |
| 463 | class `DICOMWIZARDPRO_OT_new_file` | `dicom_wizard_pro.new_file` · Back to DICOM Start |
| 469 | `DICOMWIZARDPRO_OT_new_file.invoke` |  |
| 472 | `DICOMWIZARDPRO_OT_new_file.execute` |  |
| 506 | class `DICOMWIZARDPRO_OT_auto_threshold` | `dicom_wizard_pro.auto_threshold` · Automático |
| 513 | `DICOMWIZARDPRO_OT_auto_threshold.poll` |  |
| 516 | `DICOMWIZARDPRO_OT_auto_threshold.execute` |  |
| 538 | class `DICOMWIZARDPRO_OT_reset_plane` | `dicom_wizard_pro.reset_plane` · Enderezar |
| 545 | `DICOMWIZARDPRO_OT_reset_plane.poll` |  |
| 549 | `DICOMWIZARDPRO_OT_reset_plane.execute` |  |
| 569 | class `DICOMWIZARDPRO_OT_align_mpr_from_active_plane` | `dicom_wizard_pro.align_mpr_from_active_plane` · Alinear los 3 cortes desde este plano |
| 579 | `DICOMWIZARDPRO_OT_align_mpr_from_active_plane.poll` |  |
| 583 | `DICOMWIZARDPRO_OT_align_mpr_from_active_plane.execute` |  |
| 631 | class `DICOMWIZARDPRO_OT_reset_mpr_orientation` | `dicom_wizard_pro.reset_mpr_orientation` · Restablecer orientación MPR |
| 641 | `DICOMWIZARDPRO_OT_reset_mpr_orientation.poll` |  |
| 645 | `DICOMWIZARDPRO_OT_reset_mpr_orientation.execute` |  |
| 676 | class `DICOMWIZARDPRO_OT_center_plane` | `dicom_wizard_pro.center_plane` · Centrar plano |
| 683 | `DICOMWIZARDPRO_OT_center_plane.poll` |  |
| 687 | `DICOMWIZARDPRO_OT_center_plane.execute` |  |
| 705 | class `DICOMWIZARDPRO_OT_select_target` | `dicom_wizard_pro.select_target` · Seleccionar control |
| 720 | `DICOMWIZARDPRO_OT_select_target.poll` |  |
| 724 | `DICOMWIZARDPRO_OT_select_target.execute` |  |
| 753 | `_dicom_volume_extent_mm` | Return a safe physical size used to frame the radiographic viewports. |
| 767 | `_radiographic_proxy_name` |  |
| 771 | `_radiographic_proxy_mesh_name` |  |
| 775 | `_radiographic_proxy_location` | Return an isolated world location for one flat MPR display. |
| 790 | `_get_radiographic_collection` |  |
| 798 | `_build_flat_proxy_mesh` |  |
| 833 | `_ensure_radiographic_proxy` |  |
| 872 | `_sync_radiographic_proxy` | Update an existing display proxy without creating one unnecessarily. |
| 879 | `_create_radiographic_proxies` |  |
| 886 | `_remove_radiographic_proxies` |  |
| 905 | `_region_view3d` | Return the RegionView3D owned by a concrete quad sub-region. |
| 913 | `_quad_window_regions` | Return quad regions as top-left, top-right, bottom-left, bottom-right. |
| 951 | `_prepare_independent_quad_region` |  |
| 966 | `_set_region_view_from_proxy` | Frame only the dedicated flat image panel for one MPR orientation. |
| 1009 | `_set_region_view_3d` | Configure the bottom-right quadrant as the true clinical 3D scene. |
| 1048 | `configure_radiographic_quad_view` | Configure three isolated MPR monitors plus one genuine 3D viewport. |
| 1094 | `_area_window_region` |  |
| 1098 | `_area_center_xy` |  |
| 1105 | `_area_from_pointer` |  |
| 1112 | `_area_rect` | Return an editor rectangle in window coordinates. |
| 1117 | `_rect_contains` |  |
| 1132 | `_areas_inside_rect` | Return real editors created inside one original editor rectangle. |
| 1144 | `_two_columns_in_rect` | Identify a settled left/right split by geometry, not pointer timing. |
| 1161 | `_two_rows_in_rect` | Identify a settled top/bottom split by geometry, not pointer timing. |
| 1178 | `_request_screen_area_split` | Request one UI split without assuming that screen.areas updates now. |
| 1212 | `_configure_clean_view3d_area` | Make one real 3D editor visually minimal without changing the scene. |
| 1232 | `_mpr_orientation_for_area` | Return the diagnostic role assigned to the current 3D editor area. |
| 1250 | `_mpr_slice_readout` | Convert a 0–100 slice position to index, total slices and centred mm. |
| 1261 | `draw_mpr_slice_header` |  |
| 1266 | `_is_global_mpr_area` |  |
| 1277 | `draw_mpr_global_header` | Review controls live exclusively in the add-on sidebar panel. |
| 1282 | `_set_global_mpr_local_visibility` | Hide axial/coronal only in the fourth viewport using Local View. |
| 1366 | `_set_diagnostic_mpr_local_visibility` | Isolate exactly one MPR plane in one concrete 3D editor. |
| 1397 | `_set_diagnostic_mpr_local_visibility._override` |  |
| 1480 | `_frame_object_in_axis_view` | Frame an object without invoking ``view_selected`` or smooth view. |
| 1525 | `_configure_sagittal_z_editing` | Expose only rotation editing and lock the sagittal plane to global Z. |
| 1549 | `_restore_sagittal_rotation_locks` |  |
| 1563 | `_configure_clinical_3d_editor` |  |
| 1590 | `_configure_mpr_axis_view` | Configure one independent diagnostic viewport around its own plane. |
| 1693 | `_schedule_mpr_viewport_configuration` | Configure one viewport per UI tick, then verify the complete layout. |
| 1709 | `_schedule_mpr_viewport_configuration._next_step` |  |
| 1794 | `_store_mpr_role_pointers` |  |
| 1799 | `_schedule_true_mpr_layout_build` | Build the 2×2 editor grid one split per Blender UI tick. |
| 1837 | `_schedule_true_mpr_layout_build._retry_or_fail` |  |
| 1846 | `_schedule_true_mpr_layout_build._build_next_step` |  |
| 1952 | `_verify_true_mpr_layout` | Verify four real viewports and the Z/Y/X MPR plane assignment. |
| 2036 | `_join_screen_areas` | Join two adjacent areas while keeping ``source`` alive. |
| 2065 | `_close_area_fallback` |  |
| 2088 | `_restore_true_mpr_layout` | Compatibility wrapper: schedule a reliable asynchronous close. |
| 2094 | `_area_containing_point` |  |
| 2105 | `_schedule_true_mpr_layout_close` | Collapse the 2×2 grid in reverse order, one join per UI tick. |
| 2152 | `_schedule_true_mpr_layout_close._retry` |  |
| 2160 | `_schedule_true_mpr_layout_close._finish` |  |
| 2182 | `_schedule_true_mpr_layout_close._close_next_step` |  |
| 2267 | `_safe_mpr_props` |  |
| 2276 | `_safe_mpr_window_regions` | Return the four quad-view WINDOW regions sorted by screen position. |
| 2290 | `_safe_mpr_region_roles` |  |
| 2302 | `_safe_mpr_store_region_roles` | Store process-sized UI pointers without overflowing Blender ID properties. |
| 2318 | `_safe_mpr_role_for_region` |  |
| 2328 | `_safe_mpr_find_owner_area` |  |
| 2343 | `_safe_mpr_configure_regions` | Assign exact Numpad 7/1/3 views plus a free perspective region. |
| 2385 | `_safe_mpr_save_object_visibility` |  |
| 2403 | `_safe_mpr_apply_global_visibility` | Global 3D shows volume + sagittal; 2D images are GPU overlays. |
| 2425 | `_safe_mpr_apply_two_plane_visibility` | Display axial-Z and sagittal-X image planes plus any optional mesh context. |
| 2472 | `_safe_mpr_restore_object_visibility` |  |
| 2499 | `_safe_draw_uniform_rect` |  |
| 2510 | `_safe_mpr_draw_callback` | Draw one independent MPR image and one axis slider per quad region. |
| 2594 | `_safe_mpr_add_draw_handler` |  |
| 2602 | `_safe_mpr_remove_draw_handler` |  |
| 2612 | `_safe_mpr_native_quad_active` | Return True only when this VIEW_3D space owns four native quad regions. |
| 2622 | `_safe_mpr_pick_toggle_region` | Pick the concrete WINDOW region required by SCREEN_OT_region_quadview. |
| 2657 | `_safe_mpr_toggle_native_quad` | Toggle Blender's native Ctrl+Alt+Q Quad View in a verified context. |
| 2701 | `_resolve_or_recover_mpr_surface` | Return an optional mesh used only as 3D context during MPR. |
| 2772 | `_safe_mpr_open` | Open DICOM MPR from voxel data, with optional mesh context and movable Z/X planes. |
| 2904 | `_safe_mpr_close` | Leave the single-view review and restore the previous viewer state. |
| 3019 | `_safe_mpr_region_at_mouse` |  |

## [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py)

2392 líneas · imports Blender: ninguno directo · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `_safe_mpr_schedule_native_refresh` | Schedule only the final full-resolution image after interactive preview. |
| 18 | `_safe_mpr_set_axis_percent` | Move exactly one diagnostic cut along its anatomical normal axis. |
| 68 | `_safe_mpr_set_plane_rotation` | Rotate one plane around its two in-plane DICOM-local axes. |
| 128 | `_safe_mpr_set_slider_from_mouse` |  |
| 143 | class `DICOMWIZARDPRO_OT_radiographic_quad_view` | `dicom_wizard_pro.radiographic_quad_view` · Revisión 3D con planos |
| 155 | `DICOMWIZARDPRO_OT_radiographic_quad_view.poll` |  |
| 166 | `DICOMWIZARDPRO_OT_radiographic_quad_view.invoke` |  |
| 171 | `DICOMWIZARDPRO_OT_radiographic_quad_view.execute` |  |
| 177 | class `DICOMWIZARDPRO_OT_move_review_plane` | `dicom_wizard_pro.move_review_plane` · Mover plano |
| 201 | `DICOMWIZARDPRO_OT_move_review_plane.poll` |  |
| 210 | `DICOMWIZARDPRO_OT_move_review_plane.invoke` |  |
| 235 | `DICOMWIZARDPRO_OT_move_review_plane.modal` |  |
| 311 | `DICOMWIZARDPRO_OT_move_review_plane._finish_cursor` |  |
| 318 | class `DICOMWIZARDPRO_OT_rotate_review_plane` | `dicom_wizard_pro.rotate_review_plane` · Rotar plano |
| 353 | `DICOMWIZARDPRO_OT_rotate_review_plane.poll` |  |
| 362 | `DICOMWIZARDPRO_OT_rotate_review_plane.invoke` |  |
| 397 | `DICOMWIZARDPRO_OT_rotate_review_plane.modal` |  |
| 508 | `DICOMWIZARDPRO_OT_rotate_review_plane._finish_cursor` |  |
| 515 | class `DICOMWIZARDPRO_OT_close_safe_mpr` | `dicom_wizard_pro.close_safe_mpr` · Salir de revisión |
| 522 | `DICOMWIZARDPRO_OT_close_safe_mpr.poll` |  |
| 532 | `DICOMWIZARDPRO_OT_close_safe_mpr.execute` |  |
| 538 | `_close_mpr_before_workflow_action` | Collapse native Quad View before destructive or final workflow actions. |
| 554 | class `DICOMWIZARDPRO_OT_fit_view` | `dicom_wizard_pro.fit_view` · Centrar vista |
| 560 | `DICOMWIZARDPRO_OT_fit_view.execute` |  |
| 565 | class `DICOMWIZARDPRO_OT_fit_clinical_preview` | `dicom_wizard_pro.fit_clinical_preview` · Centrar CBCT |
| 571 | `DICOMWIZARDPRO_OT_fit_clinical_preview.execute` |  |
| 576 | class `DICOMWIZARDPRO_OT_refresh` | `dicom_wizard_pro.refresh` · Actualizar |
| 582 | `DICOMWIZARDPRO_OT_refresh.execute` |  |
| 595 | class `DICOMWIZARDPRO_OT_to_segmentation` | `dicom_wizard_pro.to_segmentation` · Siguiente: segmentar |
| 601 | `DICOMWIZARDPRO_OT_to_segmentation.poll` |  |
| 605 | `DICOMWIZARDPRO_OT_to_segmentation.execute` |  |
| 661 | class `DICOMWIZARDPRO_OT_undo_last` | `dicom_wizard_pro.undo_last` · Deshacer última acción |
| 667 | `DICOMWIZARDPRO_OT_undo_last.execute` |  |
| 685 | class `DICOMWIZARDPRO_OT_back_to_viewer` | `dicom_wizard_pro.back_to_viewer` · Volver a visualización |
| 690 | `DICOMWIZARDPRO_OT_back_to_viewer.execute` |  |
| 714 | class `DICOMWIZARDPRO_OT_clear_drawings` | `dicom_wizard_pro.clear_drawings` · Borrar máscara |
| 719 | `DICOMWIZARDPRO_OT_clear_drawings.execute` |  |
| 728 | class `DICOMWIZARDPRO_OT_analyze_tissues` | `dicom_wizard_pro.analyze_tissues` · Analizar densidades |
| 733 | `DICOMWIZARDPRO_OT_analyze_tissues.execute` |  |
| 746 | class `DICOMWIZARDPRO_OT_adjust_tissue_sensitivity` | `dicom_wizard_pro.adjust_tissue_sensitivity` · Ajustar segmentación |
| 757 | `DICOMWIZARDPRO_OT_adjust_tissue_sensitivity.execute` |  |
| 795 | class `DICOMWIZARDPRO_OT_reset_tissue_range` | `dicom_wizard_pro.reset_tissue_range` · Restaurar umbrales automáticos |
| 800 | `DICOMWIZARDPRO_OT_reset_tissue_range.execute` |  |
| 814 | class `DICOMWIZARDPRO_OT_calculate_segmentation` | `dicom_wizard_pro.calculate_segmentation` · Segmentar automáticamente |
| 821 | `DICOMWIZARDPRO_OT_calculate_segmentation.execute` |  |
| 855 | class `DICOMWIZARDPRO_OT_remove_small_islands` | `dicom_wizard_pro.remove_small_islands` · Eliminar islas pequeñas |
| 860 | `DICOMWIZARDPRO_OT_remove_small_islands.execute` |  |
| 869 | class `DICOMWIZARDPRO_OT_keep_largest_island` | `dicom_wizard_pro.keep_largest_island` · Conservar isla mayor |
| 874 | `DICOMWIZARDPRO_OT_keep_largest_island.execute` |  |
| 883 | class `DICOMWIZARDPRO_OT_close_gaps` | `dicom_wizard_pro.close_gaps` · Cerrar discontinuidades |
| 888 | `DICOMWIZARDPRO_OT_close_gaps.execute` |  |
| 897 | class `DICOMWIZARDPRO_OT_fill_holes` | `dicom_wizard_pro.fill_holes` · Rellenar huecos internos |
| 902 | `DICOMWIZARDPRO_OT_fill_holes.execute` |  |
| 967 | `_begin_ai_performance_session` | Reduce only measured/reversible graphics pressure during neural inference. |
| 1014 | `_restore_ai_performance_session` |  |
| 1045 | `ai_performance_session_state` |  |
| 1049 | `_set_segmentation_progress` |  |
| 1085 | `_begin_segmentation_progress` |  |
| 1098 | `_end_segmentation_progress` |  |
| 1124 | `segmentation_progress_snapshot` |  |
| 1142 | `semantic_workflow_busy` | Return whether a clinical segmentation transaction is active. |
| 1156 | `_finish_async_segmentation` |  |
| 1215 | `_abort_async_segmentation` | Abort one transaction and remove only artifacts created by that phase. |
| 1291 | `cancel_semantic_workflow` | Cancel the active asynchronous CBCT transaction and roll it back safely. |
| 1303 | `_poll_async_segmentation` |  |
| 1652 | `_start_async_full_segmentation` | Launch the selected DSG 9.10 segmentation engine in the external worker. |
| 1745 | class `DICOMWIZARDPRO_OT_segment_semantic_structure` | `dicom_wizard_pro.segment_semantic_structure` · Segmentar estructura |
| 1754 | `DICOMWIZARDPRO_OT_segment_semantic_structure.execute` |  |
| 1777 | class `DICOMWIZARDPRO_OT_segment_all` | `dicom_wizard_pro.segment_all` · Segmentar todo |
| 1786 | `DICOMWIZARDPRO_OT_segment_all.execute` |  |
| 1804 | class `DICOMWIZARDPRO_OT_direct_dicom_to_surface` | `dicom_wizard_pro.direct_dicom_to_surface` · Segmentar DICOM |
| 1811 | `DICOMWIZARDPRO_OT_direct_dicom_to_surface.execute` |  |
| 1827 | `generate_native_alignment_reference` | Return the best available IOS↔CBCT dental reference. |
| 1918 | `generate_unsegmented_dicom_stl` | Build a native DICOM threshold STL with no neural segmentation. |
| 2015 | class `DICOMWIZARDPRO_OT_continue_with_dicom_stl` | `dicom_wizard_pro.continue_with_dicom_stl` · Continuar con STL DICOM |
| 2021 | `DICOMWIZARDPRO_OT_continue_with_dicom_stl.execute` |  |
| 2057 | class `DICOMWIZARDPRO_OT_prepare_ai_alignment` | `dicom_wizard_pro.prepare_ai_alignment` · Crear referencia dental CBCT y continuar |
| 2063 | `DICOMWIZARDPRO_OT_prepare_ai_alignment.execute` |  |
| 2105 | class `DICOMWIZARDPRO_OT_prepare_alignment` | `dicom_wizard_pro.prepare_alignment` · Continue to Alignment |
| 2111 | `DICOMWIZARDPRO_OT_prepare_alignment.execute` |  |
| 2216 | class `DICOMWIZARDPRO_OT_export_surface_stl` | `dicom_wizard_pro.export_surface_stl` · Exportar STL |
| 2227 | `DICOMWIZARDPRO_OT_export_surface_stl.invoke` |  |
| 2241 | `DICOMWIZARDPRO_OT_export_surface_stl.execute` |  |
| 2283 | class `DICOMWIZARDPRO_OT_generate_surface` | `dicom_wizard_pro.generate_surface` · Generar superficie |
| 2288 | `DICOMWIZARDPRO_OT_generate_surface.execute` |  |
| 2310 | class `DICOMWIZARDPRO_OT_select_surface` | `dicom_wizard_pro.select_surface` · Seleccionar superficie |
| 2314 | `DICOMWIZARDPRO_OT_select_surface.execute` |  |
| 2327 | class `DICOMWIZARDPRO_OT_back_to_segmentation` | `dicom_wizard_pro.back_to_segmentation` · Volver a segmentación |
| 2331 | `DICOMWIZARDPRO_OT_back_to_segmentation.execute` |  |

## [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py)

810 líneas · imports Blender: bpy · namespace de `dicom_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `_ui_error` | Keep the rest of the panel visible if one UI section fails. |
| 13 | `_draw_guarded` |  |
| 20 | `_draw_axis_controls` | Draw the six requested sliders for the active plane. |
| 39 | `_draw_visibility` |  |
| 52 | `_draw_density` |  |
| 64 | `_draw_plane_selector_and_actions` |  |
| 94 | `_draw_reset_flow_panel` | Navigation is centralized in DSG > Control del flujo (v9.2.5). |
| 99 | class `DICOMWIZARDPRO_PT_main` | `DICOMWIZARDPRO_PT_main` · DICOM |
| 110 | `DICOMWIZARDPRO_PT_main.poll` |  |
| 116 | `DICOMWIZARDPRO_PT_main.draw` |  |
| 153 | class `_DICOMChildPanel` |  |
| 161 | `_DICOMChildPanel.poll` |  |
| 169 | class `DICOMWIZARDPRO_PT_import` | `DICOMWIZARDPRO_PT_import` · DICOM |
| 176 | `DICOMWIZARDPRO_PT_import.draw` |  |
| 218 | class `DICOMWIZARDPRO_PT_view` | `DICOMWIZARDPRO_PT_view` · DICOM |
| 225 | `DICOMWIZARDPRO_PT_view.draw` |  |
| 238 | class `DICOMWIZARDPRO_PT_view_advanced` | `DICOMWIZARDPRO_PT_view_advanced` · Advanced / Avanzado |
| 248 | `DICOMWIZARDPRO_PT_view_advanced.poll` |  |
| 251 | `DICOMWIZARDPRO_PT_view_advanced.draw` |  |
| 255 | class `DICOMWIZARDPRO_PT_segment` | `DICOMWIZARDPRO_PT_segment` · DICOM |
| 262 | `DICOMWIZARDPRO_PT_segment.draw` |  |
| 429 | class `DICOMWIZARDPRO_PT_segment_advanced` | `DICOMWIZARDPRO_PT_segment_advanced` · Advanced / Avanzado |
| 437 | `DICOMWIZARDPRO_PT_segment_advanced.poll` |  |
| 440 | `DICOMWIZARDPRO_PT_segment_advanced.draw` |  |
| 444 | class `DICOMWIZARDPRO_PT_mpr_review` | `DICOMWIZARDPRO_PT_mpr_review` · DICOM |
| 451 | `DICOMWIZARDPRO_PT_mpr_review.draw` |  |
| 521 | class `DICOMWIZARDPRO_PT_result` | `DICOMWIZARDPRO_PT_result` · DICOM |
| 528 | `DICOMWIZARDPRO_PT_result.draw` |  |
| 595 | `menu_import` |  |
| 602 | `_dicom_data_access_ready` | True only after Blender has released its activation-time _RestrictData. |
| 613 | `pre_register_quiesce` | Stop old DICOM callbacks without reading any scene/object datablocks. |
| 635 | `_dicom_unregister_class_object` |  |
| 645 | `_dicom_unregister_stale_classes` | Remove RNA classes left by a previous DSG/DICOM installation. |
| 660 | `_dicom_remove_stale_scene_pointer` |  |
| 673 | `register` |  |
| 734 | `deferred_post_register` | Install data-sensitive handlers after Blender releases _RestrictData. |
| 751 | `unregister` |  |

## [_guide_parts/00_bootstrap_constants_assets_a.py](../_guide_parts/00_bootstrap_constants_assets_a.py)

899 líneas · imports Blender: bmesh, bpy, bpy_extras, gpu, mathutils · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 441 | `_register_dsg_custom_icons` |  |
| 455 | `_unregister_dsg_custom_icons` |  |
| 465 | `_dsg_custom_icon_id` |  |

## [_guide_parts/00_bootstrap_constants_assets_b.py](../_guide_parts/00_bootstrap_constants_assets_b.py)

111 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [_guide_parts/01_workflow_state_mpr_objects_a.py](../_guide_parts/01_workflow_state_mpr_objects_a.py)

2837 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 51 | `_migrate_model_implant_guide_flow` | Migrate earlier scenes to model → implants → contour. |
| 121 | `_safe_mpr_owner_area_pointer` | Return the active DICOM quad-view area pointer so DSG never rewrites it. |
| 132 | `_iter_precision_region_views` | Yield stable keys and RegionView3D objects outside the DICOM MPR area. |
| 183 | `_load_precision_view_backup` |  |
| 191 | `_store_precision_view_backup` |  |
| 199 | `activate_precision_orthographic` | Switch DSG View3D regions to ORTHO while preserving their prior mode. |
| 226 | `restore_precision_projection` | Restore projection modes saved before DSG enabled precision orthographic. |
| 253 | `_context_projection_is_orthographic` |  |
| 263 | `_workflow_closed_boundary_passes` | Return True when the audited mesh has no open boundary edges. |
| 283 | `_mark_closed_boundary_model_accepted` | Persist non-destructive acceptance of a zero-boundary dental model. |
| 309 | `_schedule_zero_boundary_auto_advance` | Advance safely outside Panel.draw when a closed model is detected. |
| 326 | `_schedule_zero_boundary_auto_advance._advance` |  |
| 370 | `_workflow_model_candidate` |  |
| 380 | `_workflow_frame_candidate` |  |
| 392 | `_workflow_guide_candidate` |  |
| 401 | `_workflow_matrix_signature` |  |
| 411 | `_workflow_object_signature` |  |
| 419 | `_workflow_implant_clinical_record` | Return a clinically stable implant pose record. |
| 461 | `_workflow_implants_signature` | Hash the clinically relevant implant plan without numerical false positives. |
| 477 | `_workflow_contour_signature` |  |
| 496 | `_workflow_checkpoint_collection_name` |  |
| 500 | `_workflow_checkpoint_state_key` |  |
| 504 | `_workflow_checkpoint_managed_object` | Return True for DSG-derived geometry that must participate in Back. |
| 554 | `_workflow_checkpoint_serializable_value` |  |
| 560 | `_workflow_checkpoint_prop_state` |  |
| 607 | `_workflow_checkpoint_scene_state` |  |
| 624 | `_clear_workflow_checkpoint` |  |
| 650 | `_clear_workflow_checkpoints_after` |  |
| 655 | `_clear_all_workflow_checkpoints` |  |
| 660 | `_capture_workflow_checkpoint` | Store the completed stage before advancing to the next one. |
| 771 | `_restore_workflow_checkpoint` | Restore exact geometry saved after completing ``step``. |
| 953 | `_workflow_stage_signature` |  |
| 970 | `_workflow_store_signature` |  |
| 979 | `_workflow_signature_changed` |  |
| 988 | `_clear_guide_outputs_for_model_change` | Clear only guide-dependent data after choosing a different IOS. |
| 1108 | `_invalidate_workflow_after` | Remove only outputs that depend on a changed upstream stage. |
| 1216 | `_workflow_contour_count` |  |
| 1229 | `_workflow_irrigation_resolved` |  |
| 1248 | `_workflow_reinforcement_resolved` |  |
| 1262 | `_workflow_requirement_report` | Audit every prerequisite needed to enter ``target_step``. |
| 1460 | `_workflow_highest_valid_step` |  |
| 1471 | `_workflow_hide_known_stage_objects` |  |
| 1487 | `_workflow_show_objects` |  |
| 1496 | `_ensure_clinical_model_material` | Neutral gray IOS/model material for Material Preview. |
| 1522 | `_apply_clinical_model_material` | Assign the model display material without touching blockout materials. |
| 1547 | `_restore_workflow_stage` | Reconstruct visibility, material preview and controllers for one stage. |
| 1663 | `_schedule_workflow_stage_restore` |  |
| 1671 | `_schedule_workflow_stage_restore._restore_timer` |  |
| 1694 | `_set_workflow_gate` |  |
| 1711 | `_require_workflow_stage` |  |
| 1769 | `_reconcile_workflow_after_undo` |  |
| 1793 | `_on_current_step_update` | Single gate for every forward/backward workflow transition. |
| 1868 | `_on_precision_ortho_lock_update` |  |
| 1880 | `_dsg_spanish` |  |
| 1884 | `_ui_text` |  |
| 1888 | `_step_text` |  |
| 1895 | `_dsg_report` |  |
| 1912 | `_suite_role` |  |
| 1915 | `_set_suite_role` |  |
| 1921 | `_find_suite_object` |  |
| 1924 | `_is_generated_blockout_mesh` | Return True for any DSG mesh that must never be reused as source anatomy. |
| 1942 | `_looks_like_dicom_mesh` | Fast name/role guard available before the full DICOM helper is defined. |
| 1956 | `_is_strict_ios_blockout_source` | Accept only an IOS scan/aligned IOS as source anatomy for blockout. |
| 1986 | `_is_closed_counterpart_of_aligned_ios` |  |
| 2000 | `_closed_counterpart` | Accepted closed model generated from this (open) IOS, if any. |
| 2010 | `_find_aligned_ios` |  |
| 2032 | `_resolve_blockout_source_model` | Resolve the IOS explicitly chosen in DSG, with a safe alignment fallback. |
| 2056 | `_is_dicom_related_object` |  |
| 2070 | `_set_solid_view_original_colors` | Return every visible 3D editor to normal Solid material colors. |
| 2100 | `_set_dicom_collections_hidden` |  |
| 2104 | `_show_dicom_objects` |  |
| 2119 | `_is_dicom_segmentation_mesh` | Segmented teeth/bone/canal meshes: heavy, never needed to read an MPR. |
| 2129 | `_show_dicom_review_objects` | DICOM review: MPR planes and helpers only, plus chosen neighbours. |
| 2155 | `_hide_dicom_objects` |  |
| 2168 | `_hide_ios_antagonists_for_insertion_axis` | Hide every registered antagonist while the insertion axis is chosen. |
| 2199 | `_show_simple_active_cbct_jaw` | For SIMPLE cases show only the large CBCT jaw island matching the IOS. |
| 2226 | `_isolate_ios_for_guide` |  |
| 2250 | `_implant_geometry_center_world` | Return the vertex centroid of an implant in world coordinates. |
| 2270 | `_is_valid_mpr_microscrew` | Return True for a DSG microscrew trajectory or visual object. |
| 2303 | `_selected_mpr_microscrew` | Resolve the microscrew the user intends to review. |
| 2341 | `_microscrew_axis_world` |  |
| 2361 | `_microscrew_center_world` | Clinical centre of the screw trajectory, not of its frame supports. |
| 2398 | `_microscrew_x_hint_world` |  |
| 2415 | `_ensure_mpr_target_visible` | Keep an implant/microscrew visible over the MPR image planes. |
| 2420 | `_ensure_mpr_target_visible._unhide_object` |  |
| 2447 | `_ensure_mpr_target_visible._walk` |  |
| 2470 | `_center_two_plane_mpr_on_microscrew` | Centre the two-plane DICOM review on a selected microscrew. |
| 2531 | `_center_two_plane_mpr_on_microscrew.percent` |  |
| 2571 | `_resolve_mpr_target_implant` |  |
| 2588 | `_center_two_plane_mpr_on_implant` | Orient DSG's two-plane MPR toward the selected implant. |
| 2631 | `_center_two_plane_mpr_on_implant.percent` |  |
| 2689 | `_mpr_implant_items` |  |
| 2702 | `_on_mpr_target_implant_change` |  |
| 2714 | `_iter_view3d_areas` | Yield (window, screen, area, space) for every live 3D viewport. |
| 2734 | `_set_material_preview_guide_view` | Restore the clean implant-planning viewport used on entering step 2. |
| 2765 | `_capture_active_view3d_state` | Capture orientation/zoom without serialising Blender RNA objects. |
| 2792 | `_restore_active_view3d_state` |  |

## [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py)

2787 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `_capture_implant_step_return_state` | Arm restoration before leaving implant planning for the contour step. |
| 39 | `_restore_implant_planning_state` | Rebuild the visible step-2 state after Back/Ctrl+Z or DICOM exit. |
| 110 | `_schedule_implant_planning_state_restore` |  |
| 118 | `_schedule_implant_planning_state_restore._restore_timer` |  |
| 148 | `_dsg_restore_implant_step_after_undo` | Undo-post bridge for the complete DSG state machine. |
| 165 | `_remove_implant_navigation_restore_handler` |  |
| 174 | `_register_implant_navigation_restore_handler` |  |
| 181 | `_dicom_review_is_active` |  |
| 186 | `_close_dicom_review_for_guide` |  |
| 199 | class `DSG_OT_SelectMPRImplant` | `dsg.select_mpr_implant` · Select Implant for MPR |
| 205 | `DSG_OT_SelectMPRImplant.execute` |  |
| 234 | class `DSG_OT_OpenOrCenterImplantMPR` | `dsg.open_or_center_implant_mpr` · Implant MPR |
| 240 | `DSG_OT_OpenOrCenterImplantMPR.execute` |  |
| 261 | class `DSG_OT_CenterSelectedMicroscrewMPR` | `dsg.center_selected_microscrew_mpr` · Center Microscrew MPR |
| 267 | `DSG_OT_CenterSelectedMicroscrewMPR.execute` |  |
| 283 | class `DSG_OT_OpenOrCenterMicroscrewMPR` | `dsg.open_or_center_microscrew_mpr` · Microscrew MPR |
| 289 | `DSG_OT_OpenOrCenterMicroscrewMPR.execute` |  |
| 311 | `_ensure_dicom_voxels` | Reload the CBCT voxels when the file says loaded but memory is empty. |
| 347 | class `DSG_OT_OpenDICOMReview` | `dsg.open_dicom_review` · Review DICOM |
| 353 | `DSG_OT_OpenDICOMReview.execute` |  |
| 421 | class `DSG_OT_CloseDICOMReview` | `dsg.close_dicom_review` · Close DICOM Review |
| 426 | `DSG_OT_CloseDICOMReview.execute` |  |
| 435 | `ensure_dsg_root_collection` | Crea/recupera la colección raíz DSG sin tocar colecciones del usuario. |
| 447 | `ensure_dsg_collection` | Crea/recupera una subcolección DSG para ordenar la escena automáticamente. |
| 466 | `unlink_object_from_dsg_collections` | Desenlaza un objeto conservado por el usuario de las colecciones internas DSG. |
| 481 | `cleanup_empty_dsg_collections` | Elimina subcolecciones DSG vacías y, opcionalmente, la raíz si queda vacía. |
| 522 | `get_dsg_collection_name_for_role` |  |
| 526 | `link_object_to_dsg_collection` | Enlaza el objeto a su colección DSG sin deshacer colecciones del usuario. |
| 556 | `register_dsg_object` | Registra un objeto sin depender de PointerProperty persistente ni roles. |
| 654 | `_dsg_action_begin` | Reject re-entrant and accidental rapid repeats of a write action. |
| 670 | `_dsg_action_end` |  |
| 682 | `_make_dsg_guarded_execute` | Return a Blender-compatible execute callback with exactly two arguments. |
| 690 | `_make_dsg_guarded_execute.guarded_execute` |  |
| 719 | `_dsg_guard_operator_class` | Wrap one operator once, without changing its clinical implementation. |
| 730 | `_install_dsg_action_guards` |  |
| 739 | `_is_numeric_duplicate_name` |  |
| 746 | `_cleanup_dsg_singleton_duplicates` | Remove only accidental .001 copies of objects that must be singletons. |
| 777 | `_cleanup_dsg_owned_orphan_data` | Purge only zero-user datablocks explicitly marked as DSG-owned. |
| 810 | `_dsg_owned_data_cleanup_timer` |  |
| 823 | `_schedule_dsg_owned_data_cleanup` |  |
| 835 | `_rounded_matrix_signature` |  |
| 842 | `_current_sleeve_build_signature` |  |
| 863 | `_sleeve_dimensions_from_props` | Return the three user-configurable sleeve dimensions in millimetres. |
| 872 | `_sleeve_dimensions_from_guide` | Read dimensions stored on a generated guide, including migrated scenes. |
| 901 | `_sleeve_dimensions_match_guide` |  |
| 912 | `_safe_object_name` | Devuelve el nombre solo cuando el StructRNA sigue vivo. |
| 927 | `_valid_obj` | Comprueba un Object de Blender sin tocar propiedades de un RNA eliminado. |
| 944 | `_inherit_dsg_custom_properties` | Copy DSG custom properties when a guide object is rebuilt. |
| 974 | `_guide_has_downstream_sleeve_evidence` | Return True when a guide can only have originated after sleeve creation. |
| 1010 | `_restore_sleeve_metadata_if_derivable` | Repair scenes whose rebuilt guide lost sleeve metadata. |
| 1050 | `find_dsg_objects` | Busca por nombre, prefijo o colección; no usa propiedades DSG_role. |
| 1054 | `find_dsg_objects.add` |  |
| 1100 | `get_primary_dsg_object` | Resuelve primero el nombre fijo y después el puntero actual como fallback. |
| 1118 | `repair_core_object_pointers` | Sincroniza solo los objetos únicos mediante sus nombres canónicos. |
| 1139 | `_clear_scene_object_pointers` | Borra PointerProperty que apunten a ``obj`` antes de eliminarlo. |
| 1169 | `_clear_id_animation_data` | Detach Actions, NLA tracks and drivers before a DSG ID is retired. |
| 1198 | `_sanitize_dsg_object_for_id_change` | Prepare a generated object before delete, archive, rename or replacement. |
| 1223 | `_prepare_outliner_for_dsg_id_changes` | Avoid Blender 5.2 expanding stale Object AnimData during DSG rebuilds. |
| 1254 | `_archive_transient_dsg_object` | Hide a temporary object without invalidating its Blender ID. |
| 1279 | `_sanitize_static_dsg_geometry_animdata` | Remove obsolete animation links before static clinical geometry stages. |
| 1294 | `safe_remove_object` | Elimina un objeto vivo después de sanear referencias y AnimData. |
| 1321 | `safe_remove_by_name` |  |
| 1328 | `safe_remove_engrave_object` | Retira un helper de grabado junto con su datablock temporal. |
| 1361 | `safe_remove_object_with_data` | Elimina un objeto temporal y su datablock huérfano cuando es seguro. |
| 1392 | `safe_remove_temp_by_name` |  |
| 1399 | `safe_remove_by_prefix` |  |
| 1405 | `deselect_all_objects` |  |
| 1410 | `set_active` |  |
| 1418 | `link_object` |  |
| 1428 | `ensure_object_mode` |  |
| 1434 | `apply_modifier_direct` |  |
| 1465 | `should_keep_sleeve_flat_faces` | Protege la geometría precisa del sleeve después de generarlo. |
| 1479 | `mark_sleeve_flat_protected` |  |
| 1490 | `continuous_fusion_remesh_enabled` | Devuelve True cuando se prioriza una guía soldada y manifold. |
| 1503 | `get_continuous_fusion_voxel` |  |
| 1512 | `add_and_apply_voxel_remesh_if_allowed` | Aplica voxel remesh solo cuando no puede alterar un sleeve protegido. |
| 1530 | `join_objects` |  |
| 1549 | `duplicate_object_with_data` |  |
| 1558 | `duplicate_evaluated_object_with_data` | Duplica la geometría evaluada para que modificadores visibles y blockout coincidan. |
| 1579 | `_world_vertex_normal` | Return a normalized world-space vertex normal without modifying the mesh. |
| 1591 | `_ensure_temporary_blockout_proxy_manifold` | Verify and, only on the temporary proxy, repair topology without remesh. |
| 1612 | `_build_blockout_addition_volume` | Create a disposable, closed proxy for surgical-guide blockout UNION. |
| 1761 | `_passive_blockout_material` |  |
| 1768 | `_assign_blockout_union_band_material` | Paint a narrow surgical-teal band where the blockout joins the source model. |
| 1881 | `_quiesce_blockout_boolean_modifiers` | Disable and remove legacy blockout Boolean modifiers without evaluation. |
| 1936 | `_blockout_class_values` | Read the point-domain retention classes written by build_blockout_bvh. |
| 1968 | `_replace_vertex_group_indices` | Create one deterministic vertex group without per-vertex Python calls. |
| 1987 | `_prepare_blockout_modifier_groups` | Create passive, retentive, blockout and transition groups. |
| 2031 | `_add_apply_passive_shrinkwrap` | Project only passive support vertices to the IOS plus guide clearance. |
| 2064 | `_add_apply_transition_relax` | Apply a real Blender Laplacian modifier only to the blockout frontier. |
| 2100 | `_clamp_blockout_modifier_result` | Prevent modifiers from weakening retention or over-rounding the frontier. |
| 2131 | `_boundary_edge_components_with_verts` |  |
| 2153 | `_cleanup_blockout_protocol_mesh` | BMesh equivalent of the supplied cleanup protocol, applied safely. |
| 2257 | `_apply_surgical_guide_blockout_modifier_protocol` | Apply the clinical passive-seat stack transactionally to one copy. |
| 2328 | `_boolean_rescue_passive_model` | Last-resort Boolean with a 0.01-0.03 mm disposable local overlap. |
| 2365 | `build_joined_passive_model` | Create the v7-compatible passive cutter from evaluated IOS + blockout. |
| 2427 | `get_confirmed_passive_model_obj` | Return only the explicitly confirmed passive/retentive cutter. |
| 2447 | `get_passive_model_obj` | Return the best passive-model reference for non-gating geometry tools. |
| 2465 | `_set_obj_hidden` |  |
| 2476 | `prepare_final_cut_references` | Prepara las referencias del corte final sin esconder objetos auxiliares. |
| 2500 | `_object_is_hidden` |  |
| 2509 | `_toggle_visibility_for_objects` |  |
| 2524 | `get_blockout_visibility_objects` | Devuelve únicamente el modelo pasivo final para la revisión clínica. |
| 2560 | `get_guide_visibility_objects` |  |
| 2578 | `get_axis_empty` |  |
| 2582 | `get_pending_implant_axis_empty` | One-shot implant axis proposed from FDI without altering guide insertion. |
| 2595 | `consume_pending_implant_axis_empty` |  |
| 2607 | `invalidate_pending_implant_axis_empty` | Invalidate an advisory FDI axis so stale geometry cannot be consumed. |
| 2633 | `hide_axis_empty` | Oculta DSG_Axis sin eliminarlo para conservar su orientación interna. |
| 2671 | `ensure_axis_empty` |  |
| 2684 | `_view3d_window_region` | Return the actual viewport WINDOW region, even when invoked from the N-panel. |
| 2694 | `_world_bbox_center` |  |
| 2704 | `_view_reference_target` | Find the surface point at the centre of the user's current viewport. |
| 2730 | `capture_insertion_view_reference` | Capture the complete user view used to define guide insertion. |

## [_guide_parts/02_implant_animation_geometry_a.py](../_guide_parts/02_implant_animation_geometry_a.py)

3070 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `orient_empty_to_vector` |  |
| 6 | `get_insertion_axis` |  |
| 15 | `_read_stored_world_axis` |  |
| 33 | `store_blockout_axis` | Persist the exact world-space vector used to survey the model. |
| 57 | `current_blockout_axis` | Read the currently visible arrow and freeze that exact vector. |
| 67 | `preview_blockout_axis` | Return the vector used by the selected preview. |
| 90 | `object_bbox_diagonal` |  |
| 99 | `build_axis_basis` |  |
| 107 | `sort_contour_points` |  |
| 111 | `sort_contour_points.ang` |  |
| 117 | `make_cylinder_mesh` |  |
| 128 | `make_torus_mesh` | Torus analítico local alineado con Z para manifolds internos de irrigación. |
| 165 | `_decode_implant_template` | Decodifica una sola vez la plantilla STL optimizada integrada en el addon. |
| 191 | `make_embedded_implant_mesh` | Crea la representación visual del implante desde el STL integrado. |
| 217 | `_decode_drill_visual_template` | Decodifica una sola vez la fresa optimizada integrada en el addon. |
| 242 | `_reduce_and_rectify_drill_mesh` | Reduce la triangulación y rectifica el cilindro/tope de la fresa. |
| 342 | `_percentile_sorted` |  |
| 355 | `_interpolate_profile` |  |
| 378 | `_straighten_drill_axis` | Elimina la curvatura heredada del STL sin destruir las hélices. |
| 435 | `_rebuild_upper_cylindrical_body` | Reconstruye la parte superior como cilindros lisos con ángulos rectos. |
| 505 | `_add_ring_vertices` |  |
| 515 | `_connect_rings_quads` |  |
| 530 | `_cap_ring_with_center` |  |
| 545 | `_overlay_simple_symmetric_upper_body` | Superpone una anatomía superior simple, recta y totalmente simétrica. |
| 637 | `make_embedded_drill_visual_mesh` | Crea una fresa visual paramétrica a partir del STL integrado. |
| 714 | `max_visible_turns` | Turns that keep the spin readable (no wagon-wheel effect). |
| 719 | `_action_fcurve_collections` | F-Curve collections of an Action in Blender 4.x (legacy) and 5.x (slotted). |
| 741 | `_action_fcurves` |  |
| 748 | `_remove_action_fcurve` |  |
| 756 | `_set_fcurve_interpolation_linear` |  |
| 771 | `_insert_helical_segment` |  |
| 805 | `apply_clockwise_helical_animation` | Avanza y gira sobre el eje longitudinal real de la inserción. |
| 836 | `apply_clockwise_helical_roundtrip_animation` | La fresa entra al sleeve y luego regresa a su posición inicial. |
| 879 | `ensure_animated_drill_material` |  |
| 893 | `_set_constant_interpolation_for_data_paths` |  |
| 909 | `clear_implant_drill_visibility_animation` |  |
| 929 | `animate_implants_hidden_until` | Oculta todos los implantes durante la secuencia y los revela juntos al final. |
| 961 | `_matrix_to_flat_list` |  |
| 966 | `_matrix_from_flat_list` |  |
| 979 | `_store_implant_final_transform` |  |
| 993 | `clear_implant_insertion_animation` | Remove only animation curves created by the final insertion sequence. |
| 1042 | `_find_tooth_object_for_fdi` |  |
| 1059 | `_immediate_extraction_animation_sources` | Return hidden/registered teeth that should be animated out first. |
| 1101 | `_copy_object_material_slots` |  |
| 1113 | `_estimate_extraction_axis_and_travel` | Estimate a crown-ward extraction vector from the tooth geometry itself. |
| 1168 | `_estimate_extraction_axis_and_travel._end_width` |  |
| 1202 | `clear_animated_extraction_teeth` |  |
| 1224 | `get_animated_extraction_tooth_objects` |  |
| 1234 | `build_animated_extraction_tooth` | Create a visible duplicate of the virtually extracted tooth and animate it out. |
| 1338 | `get_animated_implant_objects` |  |
| 1347 | `_implant_start_location_above_sleeve` | Places the complete implant immediately above the occlusal sleeve face. |
| 1384 | `animate_implant_screw_in_after_drill` | Reveal the implant above its sleeve and screw it into its planned pose. |
| 1448 | `animate_implant_hidden_during_drill` |  |
| 1453 | `get_animated_drill_objects` |  |
| 1461 | `remove_animated_drills` |  |
| 1482 | `_rotation_for_drill_on_sleeve` | Orienta +Z local de la fresa hacia la entrada oclusal del sleeve. |
| 1506 | `build_animated_drill_for_implant` | Crea y anima una fresa coaxial calibrada contra el lumen del sleeve. |
| 1631 | `_decode_microscrew_visual_template` | Decodifica la malla compacta integrada del microtornillo. |
| 1668 | `_normalized_microscrew_dimensions` |  |
| 1680 | `_microscrew_dimensions_from_props` |  |
| 1686 | `_microscrew_dimensions_from_record` |  |
| 1693 | `make_embedded_microscrew_visual_mesh` | Create the embedded screw STL at the selected clinical dimensions. |
| 1721 | `ensure_animated_microscrew_material` | Distinct metallic violet for every visual microscrew. |
| 1747 | `get_animated_microscrew_objects` | Returns every DSG animated microscrew, including renamed stale copies. |
| 1767 | `get_static_microscrew_visual_objects` | Returns planning-only screws that must not coexist with animation copies. |
| 1795 | `set_static_microscrew_visuals_hidden` | Hide planning screws while animated copies exist, preserving user state. |
| 1851 | `remove_pending_microscrew_geometry_previews` | Remove stale pending sleeve/support previews, including ``.001`` copies. |
| 1870 | `remove_pending_microscrew_visuals` | Remove every pending visual copy, not only the exact unsuffixed name. |
| 1886 | `remove_animated_microscrews` |  |
| 1896 | `invalidate_microscrew_animation` | Discard animation copies after a placement changes. |
| 1911 | `_rotation_for_microscrew_axis` | Orienta +Z local hacia la entrada coronal del sleeve. |
| 1931 | `build_static_microscrew_visual` | Crea el STL visual del microtornillo ya asentado sobre el sleeve. |
| 1986 | `build_animated_microscrew` | Crea el tornillo STL y anima su inserción coaxial hasta el asiento. |
| 2068 | `append_microscrew_unscrew_animation` | Appends a reverse helical motion that removes an inserted microscrew. |
| 2121 | `_matrix_from_flat_16` |  |
| 2133 | `_matrix_to_flat_16` |  |
| 2138 | `store_guide_home_matrix` | Stores the seated world transform once and shares it with replacement guides. |
| 2169 | `get_guide_home_matrix` |  |
| 2181 | `restore_guide_home_transform` | Returns the guide to its immutable seated position regardless of timeline state. |
| 2203 | `_keyframe_guide_world_matrix` | Assigns a world matrix, then keys the resulting local transform safely. |
| 2212 | `clear_final_guide_visibility_animation` | Removes only final-sequence keys and restores the immutable seated guide. |
| 2245 | `_guide_axis_animation_offset_mm` |  |
| 2257 | `animate_guide_seating_and_return` | Animates around an immutable seated guide transform. |
| 2327 | `make_frustum_mesh` | Crea un tronco de cono cerrado orientado sobre Z local. |
| 2355 | `make_annular_cylinder_mesh` | Create a closed annular sleeve, optionally with a manifold lateral opening. |
| 2425 | `_current_view_forward_world` | Return the current viewport forward vector, or the insertion axis. |
| 2443 | `_sleeve_lateral_opening_angle` | Angle of the lateral access facing the clinician's chosen view. |
| 2455 | `_normalize_angle_2pi` |  |
| 2459 | `_irrigation_entry_implant_name` |  |
| 2469 | `_sleeve_window_irrigation_signature` | Stable signature of the geometry that can constrain a lateral window. |
| 2507 | `_window_mark_occupied_bins` |  |
| 2518 | `_window_largest_free_run` | Return start index and length of the largest circular free interval. |
| 2548 | `_window_point_angle_and_radius` |  |
| 2557 | `_window_mark_world_point` |  |
| 2567 | `_sleeve_window_entries_for_implant` |  |
| 2575 | `_resolve_lateral_window_for_implant` | Resolve a safe window from actual irrigation geometry or the saved view. |
| 2745 | `_sleeve_window_requires_irrigation_rebuild` |  |
| 2758 | `build_combined_mesh_object_world` | Combina copias geométricas en una sola malla sin ``bpy.ops.object.join``. |
| 2805 | `store_analytic_solid_preflight` | Marca una primitiva generada por DSG como solid sin recorrer sus edges. |
| 2825 | `make_uv_sphere_mesh` |  |
| 2838 | `choose_raycast_target` |  |
| 2848 | `_transfer_bm` |  |
| 2859 | `_mesh_nonmanifold_info_from_mesh` | Chequeo ligero de no-manifold sin entrar en Edit Mode. |
| 2903 | `get_mesh_solid_report` | Verifica si una malla se comporta como sólido cerrado para booleanos. |
| 2943 | `get_mesh_solid_report_scalable` | Verificación manifold para resultados grandes, ejecutada solo bajo demanda. |
| 3044 | `_closed_manifold_geometry_signature` | CRC signature tying a successful audit to the complete mesh geometry. |

## [_guide_parts/02_implant_animation_geometry_b.py](../_guide_parts/02_implant_animation_geometry_b.py)

3069 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `get_closed_manifold_gate_report` | Strict one-shot topology audit used as the gate to the implant step. |
| 155 | `store_closed_manifold_gate_report` | Persist a gate result without treating it as valid after mesh changes. |
| 176 | `load_closed_manifold_gate_report` |  |
| 191 | `certify_closed_manifold_for_next_step` | Return a fresh or signature-valid certification and store it on obj. |
| 202 | `_closed_manifold_gate_details` |  |
| 223 | `_source_model_passes_closed_manifold_gate` |  |
| 239 | `_restore_selection_after_mesh_tool` | Restaura selección/modo tras usar operadores de limpieza de Blender. |
| 263 | `_model_topology_cache_key` | Stable in-session key for a model topology audit. |
| 282 | `_clear_model_topology_cache` |  |
| 286 | `get_model_topology_report_cached` | Return a cached solid/boundary report suitable for the UI. |
| 353 | `_boundary_edge_components` | Connected components of BMesh boundary edges. |
| 373 | `_ordered_closed_boundary_loop` | Order one degree-two boundary component; return None for branched rims. |
| 406 | `_boundary_component_perimeter` |  |
| 414 | `_safe_percentile` | Percentile helper that tolerates empty/invalid numerical collections. |
| 426 | `_robust_mad` | Median absolute deviation in model units. |
| 440 | `_object_average_world_scale` | Return a conservative local-to-world scale for millimetre parameters. |
| 454 | `_mm_to_object_units` |  |
| 458 | `_surface_samples_for_base_orientation` | Area-weighted deterministic samples of the dental surface. |
| 499 | `_robust_weighted_pca` | Huber-reweighted PCA used only to initialise the dental frame. |
| 532 | `_numpy_unit` |  |
| 541 | `_numpy_perpendicular_frame` |  |
| 551 | `_local_insertion_axis_for_base` | Optional tie-breaker only; base direction remains independent clinically. |
| 568 | `_local_world_vertical_axis_for_base` | Return the global +Z axis expressed in local mesh coordinates. |
| 589 | `_mean_boundary_normal_axis` | Average the face normals around the open rim. |
| 620 | `_section_area_proxy` | Stable cross-section proxy based on robust in-plane extents. |
| 642 | `_score_dental_base_direction` | Score one basal-axis candidate; lower is better. |
| 718 | `_tilted_axis` |  |
| 728 | `_robust_open_margin_plane_axis` | Return the normal of a robust best-fit plane through the open IOS margin. |
| 784 | `_estimate_dental_base_direction` | Define the basal vertical only from the open model margin. |
| 851 | `_automatic_base_direction` | Compatibility wrapper for the robust dental-frame estimator. |
| 870 | `_relax_closed_ring_positions` | Regularise one closed ring without changing its basal plane. |
| 895 | `_signed_polygon_area_2d` |  |
| 904 | `_resample_closed_polygon_2d_exact` | Uniformly resample a closed 2-D polygon to ``count`` points. |
| 936 | `_aligned_star_base_ring` | Create a simple star-shaped footprint with one point per rim vertex. |
| 968 | `_margin_proxy_roughness_2d` | Return a scale-independent local roughness estimate for one cyclic rim. |
| 988 | `_regularized_margin_proxy_positions` | Create a smooth duplicated basal collar without moving the scan rim. |
| 1065 | `_close_main_boundary_with_planar_base` | Create a deterministic manifold base without touching scan coordinates. |
| 1145 | `_close_main_boundary_with_planar_base.bridge_equal_rings` | Bridge every corresponding edge or fail transactionally. |
| 1359 | `_orthonormal_base_frame` | Return two stable in-plane axes perpendicular to ``direction``. |
| 1377 | `_convex_hull_2d` | Monotonic-chain convex hull used as a robust basal silhouette. |
| 1389 | `_convex_hull_2d.cross` |  |
| 1406 | `_polygon_area_2d` |  |
| 1415 | `_radial_envelope_polygon_2d` | Robust star-shaped footprint that rejects isolated scan spikes. |
| 1468 | `_derive_dental_base_footprint` | Choose a robust dental footprint and fall back to convex hull safely. |
| 1492 | `_simplify_closed_2d_polygon` | Remove near-collinear points while retaining a closed dental footprint. |
| 1526 | `_base_perimeter_material` |  |
| 1538 | `_base_perimeter_curve` |  |
| 1543 | `_remove_base_perimeter_curve` |  |
| 1549 | `_set_base_perimeter_curve_points` | Create/update the visible perimeter used by the base closure fallback. |
| 1583 | `_base_perimeter_world_points` |  |
| 1605 | `_base_perimeter_local_points` |  |
| 1618 | `_smooth_closed_polygon_2d` |  |
| 1638 | `_resample_closed_polygon_2d` |  |
| 1668 | `_expand_polygon_radially` |  |
| 1682 | `_drawn_base_footprint` |  |
| 1706 | `_raycast_model_from_event` |  |
| 1733 | `_automatic_base_outline_world` | Build the same automatic footprint used by the volumetric closure. |
| 1793 | class `DSG_OT_PreviewAutomaticBasePerimeter` | `dsg.preview_automatic_base_perimeter` · Preview Automatic Base Perimeter |
| 1799 | `DSG_OT_PreviewAutomaticBasePerimeter.execute` |  |
| 1819 | class `DSG_OT_DrawBasePerimeter` | `dsg.draw_base_perimeter` · Draw Base Perimeter |
| 1831 | `DSG_OT_DrawBasePerimeter._finish` |  |
| 1844 | `DSG_OT_DrawBasePerimeter.modal` |  |
| 1879 | `DSG_OT_DrawBasePerimeter.invoke` |  |
| 1897 | class `DSG_OT_ClearBasePerimeter` | `dsg.clear_base_perimeter` · Clear Base Perimeter |
| 1903 | `DSG_OT_ClearBasePerimeter.execute` |  |
| 1908 | `_append_base_prism_to_bmesh` | Append a closed prism that overlaps the basal scan and guarantees volume. |
| 1935 | `_run_voxel_remesh_operator` | Hard-disabled for dental-model base closure. |
| 1947 | `_reproject_anatomical_surface_to_scan` | Recover scan detail after volumetric reconstruction without reopening it. |
| 1997 | `_close_open_model_volumetric` | Robust dental-model closure using silhouette + overlapping solid + VDB. |
| 2185 | `_remove_safe_duplicate_faces_and_wire_edges` | Remove only topology that has no anatomical surface value. |
| 2223 | `_weld_exact_boundary_duplicates` | Weld only coincident vertices on open borders, without moving anatomy. |
| 2254 | `_select_boundary_candidate` | Choose a clean existing rim without rebuilding the dental surface. |
| 2298 | `_component_vertices` | Unique vertices belonging to one connected boundary component. |
| 2311 | `_select_main_open_component` | Protect the basal opening while secondary scan holes are repaired. |
| 2357 | `_fill_secondary_scan_holes_bmesh` | Fill every non-basal boundary cycle without altering scan coordinates. |
| 2431 | `close_scanned_model_holes` | Create an anatomy-locked copy with secondary scan holes capped. |
| 2510 | class `DSG_OT_CloseScanHoles` | `dsg.close_scan_holes` · Close Scan Holes |
| 2518 | `DSG_OT_CloseScanHoles.execute` |  |
| 2559 | `_verify_original_anatomy_vertices_unchanged` | Verify preservation of the *surface anatomy* without false failures. |
| 2714 | `_split_non_manifold_edges_preserve_coordinates` | Split branching edges without moving the dental surface. |
| 2737 | `_split_branched_boundary_junctions` | Separate boundary loops that touch at a vertex, without moving them. |
| 2765 | `_fill_boundary_component_topology_only` | Triangulate one simple boundary cycle using only new faces. |
| 2821 | `_fill_all_remaining_boundary_cycles` | Close every remaining simple cycle after the basal wall is generated. |
| 2840 | `_repair_residual_topology_globally` | Repair every safely repairable residual topology component. |
| 2879 | `_close_open_model_direct` | Close the model by adding only secondary-hole caps and basal geometry. |

## [_guide_parts/02_implant_animation_geometry_c.py](../_guide_parts/02_implant_animation_geometry_c.py)

2321 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `_smooth_boundary_to_plane` |  |
| 22 | `_close_open_model_flatten_remesh` | Last-resort Easy-Dental-style closure: flatten open vertices then remesh. |
| 120 | `close_open_dental_model_base` | Close an open dental model without reconstructing its anatomy. |
| 167 | class `DSG_OT_AcceptClosedIOSModel` | `dsg.accept_closed_ios_model` · Use Closed IOS Model and Continue |
| 175 | `DSG_OT_AcceptClosedIOSModel.execute` |  |
| 232 | class `DSG_OT_CloseModelBase` | `dsg.close_model_base` · Close Model Base Automatically |
| 245 | `DSG_OT_CloseModelBase.execute` |  |
| 297 | `run_3d_print_make_manifold` | Intenta ejecutar el Make Manifold real de Blender/3D Print Toolbox. |
| 338 | `make_mesh_manifold_bmesh` | Fallback interno: limpia la malla y rellena bordes abiertos pequeños/medios. |
| 408 | `verify_solid_and_make_manifold_before_drill` | Preflight del paso 9 antes de generar canales centrales. |
| 453 | `_mesh_preflight_fingerprint` |  |
| 465 | `_preflight_storage_key` |  |
| 470 | `store_boolean_preflight` |  |
| 486 | `load_boolean_preflight` |  |
| 499 | `_preflight_from_report` |  |
| 537 | `evaluate_boolean_preflight` | Chequeo no destructivo cacheado en memoria para el semáforo del panel. |
| 552 | `run_boolean_preflight` | Comprueba una malla y, si hace falta, intenta una reparación limitada. |
| 595 | `combine_boolean_preflights` |  |
| 637 | `clean_boolean_cutter_mesh` | Limpieza ligera para cutters generados por el addon. |
| 679 | `set_boolean_exact_options` | Activa opciones de tolerancia si existen en el build de Blender. |
| 692 | `apply_boolean_modifier_smart` | Aplica una booleana EXACT una sola vez. |
| 719 | `apply_boolean_difference_fast` | Alias histórico: actualmente siempre aplica DIFFERENCE con EXACT. |
| 732 | `apply_boolean_union_exact` | Fusiona dos sólidos con un único Boolean UNION robusto. |
| 758 | `_restore_object_mesh_copy` | Restaura una copia de malla y elimina la malla descartada si queda huérfana. |
| 776 | `fuse_additions_into_base_exact` | Fusiona adiciones con UNION EXACT y valida el resultado BRUTO. |
| 880 | `sleeve_sidewall_guard_enabled` | Compatibilidad de nombre: activa la validación analítica de caras planas. |
| 889 | `_sleeve_inner_radius_from_props` | Single source of truth for the sleeve lumen, independent of implant size. |
| 894 | `_sleeve_radii_from_props` |  |
| 901 | `_sleeve_flat_face_guard_values` | Márgenes de validación analítica; ya no generan cutters anulares. |
| 911 | `get_sleeve_sidewall_zone` | Devuelve la cara plana anular del sleeve más cercana a ``point``. |
| 980 | `is_point_near_protected_sleeve_sidewall` | Compatibilidad: True si el punto está cerca de una cara plana protegida. |
| 988 | `get_irrigation_base_outer_radius_at_sleeve` | Radio exterior normal del conducto en la salida estrecha del sleeve. |
| 1004 | `get_irrigation_outer_radius_at_sleeve` | Radio real de la base volcánica donde el tubo se funde con el sleeve. |
| 1025 | `get_irrigation_coronal_port_offset_mm` | Exact centre offset needed to leave the outer wall flush to the face. |
| 1044 | `get_irrigation_coronal_sleeve_z_local` | Places the port so its external wall is tangent to the coronal face. |
| 1062 | `_irrigation_direct_sleeve_overlap_mm` | Depth of a DIRECT irrigation port inside the axial sleeve lumen. |
| 1084 | `get_direct_irrigation_lumen_tip` | Return the clinical DIRECT-mode inner end point. |
| 1103 | `_irrigation_is_direct_channel_mode` |  |
| 1110 | `_normalize_direct_irrigation_controls` | Fix legacy DIRECT paths whose first point was saved at the sleeve axis. |
| 1126 | `get_sleeve_lateral_port_geometry` | Puerto seguro sobre la superficie cilíndrica lateral del sleeve. |
| 1178 | `get_sleeve_lateral_port_geometry.world_at` |  |
| 1212 | `get_sleeve_apical_port_geometry` | Alias heredado de v24: ahora devuelve un puerto lateral seguro. |
| 1220 | `append_cylinder_to_bmesh` | Añade un cilindro cutter directamente en coordenadas mundo. |
| 1238 | `build_multi_cylinder_cutter` | Crea un único objeto cutter con todos los canales de implante. |
| 1272 | `append_profiled_drill_cutter_to_bmesh` | Añade un cutter axial cerrado con radios variables. |
| 1323 | `build_safe_drill_cutter` | Crea el cutter seguro del paso 9 sin superficies coplanares con el sleeve. |
| 1406 | `get_drill_protection_radii` | Devuelve radio clínico, radio booleano y sobrecorte anti-coplanar. |
| 1430 | `build_drill_insertion_protection_cutters` | Crea cilindros coaxiales para limpiar físicamente el eje de fresado. |
| 1501 | `build_sleeve_face_clearance_cutters` | Create annular cutters only over each sleeve's flat occlusal face. |
| 1569 | `_component_is_sleeve_shell_for_implant` | Recognize the exact loose sleeve shell so the flat face is never cut. |
| 1625 | `find_sleeve_shell_implant` | Return the implant whose exact sleeve shell matches this loose component. |
| 1642 | `component_is_any_sleeve_shell` | Return True when a loose guide component is the exact sleeve shell. |
| 1647 | `_angle_degrees_from_xy` |  |
| 1656 | `_cluster_circular_angles_degrees` | Cluster polar angles while handling the 0/360° seam. |
| 1694 | `_cluster_span_degrees` |  |
| 1700 | `cutter_has_c_sleeve_manifold` | True when the cutter is intended to create the open-C sleeve manifold. |
| 1724 | `irrigation_sleeve_raycast_preflight` | Validate a C-irrigation cutter before it is allowed to touch a sleeve. |
| 1899 | `_irrigation_entry_channel_mode` | Return the saved irrigation channel mode for an entry without touching UI state. |
| 1915 | `_deduplicate_irrigation_lumen_samples` | Clean water-lumen samples without ever expanding to the tube wall. |
| 1933 | `_irrigation_resolve_implant_for_entry` | Resolve the implant used by the irrigation entry without guessing from UI state. |
| 1958 | `_irrigation_internal_sleeve_manifold_sample_groups` | Return sample groups for the final water lumen that lives inside the sleeve. |
| 2037 | `_irrigation_model_preflight_sample_groups` | Build every final water-lumen segment checked by the preflight. |
| 2083 | `_irrigation_model_preflight_samples` | Compatibility: flattened complete water-lumen sample list. |
| 2091 | `_irrigation_sample_tangent` |  |
| 2109 | `irrigation_model_cut_preflight` | Preflight the exact irrigation water lumen against the passive model. |

## [_guide_parts/03_blockout_frame_geometry_a.py](../_guide_parts/03_blockout_frame_geometry_a.py)

3190 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `irrigation_sleeve_guard_enabled` | Protect exact sleeve shells from C-shaped irrigation Booleans. |
| 8 | `apply_sleeve_face_clearance_to_components` | Clear only the flat annular drill-stop seating surface while preserving sleeve components. |
| 67 | `repair_manifold_difference_boundary` | Close small accidental rims left by Blender MANIFOLD Boolean. |
| 140 | `apply_difference_manifold_checked` | Apply one transactional MANIFOLD difference without invoking EXACT. |
| 212 | `apply_drill_insertion_protection_to_components` | Apply axial protection with one combined MANIFOLD cut per component. |
| 258 | `protect_guide_drill_insertion_transactional` | Limpia el eje sobre la guía y las paredes de irrigación por Boolean. |
| 429 | `cleanup_drill_boolean_result` | Limpieza topológica mínima tras el boolean del canal. |
| 495 | `restore_guide_mesh_from_backup` | Restaura la guía si un boolean produce bordes abiertos/no manifold. |
| 519 | `_read_render_depth_pass` | Read the one-channel Z pass produced by Blender's Render Result. |
| 550 | `_render_orthographic_ios_depth` | Rasterize the aligned IOS triangles from the insertion direction. |
| 701 | `_sample_raster_depth` | Sample direct pixels, then a one-pixel nearest-envelope fallback. |
| 741 | `_simple_axis_blockout_analysis` | Accurate blockout survey from a cached orthographic triangle Z buffer. |
| 808 | `_simple_axis_blockout_analysis.orientation_score` |  |
| 884 | `_vertex_grid_blockout_analysis_legacy` | Return a fast, single-valued insertion envelope for the aligned IOS. |
| 1036 | `_write_mesh_point_attribute` | Write one point-domain attribute with foreach_set when available. |
| 1053 | `_retention_material` |  |
| 1064 | `_retention_level` |  |
| 1072 | `_retention_engagement_mm` |  |
| 1076 | `_retention_clearance_mm` |  |
| 1080 | `_retention_draft_angle_deg` |  |
| 1084 | `_retention_fraction` | Backward-compatible fraction stored in older DSG files. |
| 1089 | `_blockout_matches_retention_settings` |  |
| 1103 | `_retention_preview_object` |  |
| 1110 | `_selected_retention_preview` |  |
| 1114 | `_retention_previews_ready` |  |
| 1123 | `_remove_retention_previews` |  |
| 1141 | `_show_selected_retention_preview` |  |
| 1173 | `_build_all_retention_previews` | Build LOW/MEDIUM/HIGH from one immutable model and insertion view. |
| 1226 | `_create_max_retention_marker` | Mark the exact deepest safe undercut selected for frame drawing. |
| 1269 | `_survey_retention_zones` | Locate the real maximum usable undercut and define one retention zone. |
| 1339 | `_blockout_retention_class` |  |
| 1355 | `_remove_retention_boundary` |  |
| 1361 | `_set_retention_boundary_visible` |  |
| 1375 | `_retention_boundary_material` |  |
| 1384 | `_retention_boundary_polylines` | Extract the height-of-contour line where blockout displacement begins. |
| 1463 | `_retention_boundary_polylines.node_key` |  |
| 1487 | `_retention_boundary_polylines.consume_chain` |  |
| 1535 | `_retention_boundary_metrics_fast` | Return inexpensive perimeter metrics directly from crossing mesh edges. |
| 1549 | `_retention_boundary_metrics_fast.find` |  |
| 1560 | `_retention_boundary_metrics_fast.union` |  |
| 1594 | `_create_retention_boundary_object` |  |
| 1631 | `_directional_survey_proxy_analysis` | Build a dense insertion-envelope proxy perpendicular to ``axis``. |
| 1700 | `_directional_survey_proxy_analysis.shifted` |  |
| 1769 | `_get_cached_blockout_analysis` | Survey one model + insertion axis and reject non-clinical ray artefacts. |
| 2120 | `_smooth_blockout_displacement` | Smooth only the scalar blockout field, never the original anatomy. |
| 2149 | `_limit_blockout_displacement_gradient` | Limit impossible per-edge jumps in the axial displacement field. |
| 2175 | `_shrinkwrap_proxy_relax_displacement` | Regularise only the true blockout frontier and keep anatomy anchored. |
| 2304 | `_scientific_blockout_profile` | Resolve hidden clearance/engagement values from whole-arch geometry. |
| 2358 | `_blockout_insertion_metrics` | Measure the axial undercut remaining after the current blockout field. |
| 2383 | `_raise_neighbours_for_blockout_gradient` | Propagate required correction outward without reducing a validated point. |
| 2419 | `_smooth_blockout_correction_upward` | Blend the automatic correction while never decreasing blockout. |
| 2440 | `_auto_correct_blockout_insertion` | Automatically project the blockout into a valid axial insertion envelope. |
| 2553 | `_mesh_world_coordinates` |  |
| 2560 | `_mesh_world_vertex_normals` |  |
| 2570 | `_blockout_base_face_mask` | Faces of the artificial closed base: long rim-to-cap walls and the cap. |
| 2592 | `_anatomy_vertex_mask` | Vertices that belong to at least one anatomical (non-base) face. |
| 2604 | `_anatomy_bvh` |  |
| 2617 | `_evaluated_mesh_for_blockout` |  |
| 2628 | `build_blockout_bvh` | Blockout v8: el raycast sencillo de v7, con evaluación, filtros y estadísticas. |
| 2813 | `_set_principled_input` | Assign a Principled input across Blender 4/5 naming differences. |
| 2829 | `_blockout_zone_visual_material` | Clinical teal material used only to review the added blockout surface. |
| 2851 | `_ensure_blockout_zone_visual` | Create a non-exportable overlay containing only blockout-added faces. |
| 2972 | `is_valid_implant_obj` |  |
| 2981 | `get_all_implant_objects` | Devuelve todos los implantes DSG presentes en escena, sin duplicados. |
| 2998 | `count_implants` |  |
| 3002 | `irrigation_implant_is_sealed` | Return the persisted selective-irrigation state for one implant. |
| 3017 | `set_irrigation_implant_sealed` |  |
| 3029 | `auto_assign_irrigation_gate_defaults` | Keep the first irrigated implant open and seal every later outlet. |
| 3069 | `irrigation_path_implant_names` | Names of implants that actually have a confirmed irrigation branch. |
| 3082 | `get_sealed_irrigation_implants` |  |
| 3094 | `sync_irrigation_gate_metadata` | Store a portable summary on the guide without creating geometry. |
| 3118 | `get_implant_nominal_diameter_world` | Diámetro clínico del implante, incluyendo una posible escala XY del objeto. |
| 3135 | `get_implant_platform_center_world` | Centro world-space de la plataforma coronal (extremo +Z local). |
| 3148 | `measure_interimplant_platform_clearance` | Mide la distancia libre horizontal entre plataformas adyacentes. |

## [_guide_parts/03_blockout_frame_geometry_b.py](../_guide_parts/03_blockout_frame_geometry_b.py)

2910 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `get_interimplant_spacing_results` |  |
| 12 | `get_interimplant_spacing_violations` |  |
| 20 | `get_implant_safety_halos` |  |
| 30 | `clear_implant_safety_halos` | Retires halos without deleting their Object IDs during the workflow. |
| 47 | `_implant_safety_halo_name` |  |
| 51 | `_replace_mesh_data_preserve_object` |  |
| 64 | `create_implant_safety_halo` |  |
| 69 | `rebuild_implant_safety_halos` | Reuse one stable halo Object per implant instead of delete/recreate loops. |
| 90 | `mark_implant_safety_halos` |  |
| 113 | `get_implant_tooth_safety_results` | Return implant↔tooth clearance results for implants with a valid target FDI. |
| 163 | `get_implant_tooth_safety_violations` |  |
| 167 | class `DSG_OT_AnalyzeImplantSafety` | `dsg.analyze_implant_safety` · Analyze Implant Safety |
| 172 | `DSG_OT_AnalyzeImplantSafety.execute` |  |
| 201 | `_get_emergence_controller_for_implant` |  |
| 209 | `select_interimplant_violation` | Selecciona los dos controles implicados para que el usuario pueda separarlos. |
| 234 | `get_implant_emergence_tubes` |  |
| 248 | `_detach_implant_from_emergence_tube` | Preserves the edited implant pose before removing its temporary controller. |
| 279 | `clear_implant_emergence_tubes` | Detach and archive controllers; do not delete IDs during clinical flow. |
| 294 | `remove_implant_emergence_tubes_for_implant` | Removes only the temporary emergence controller linked to one implant. |
| 333 | `_emergence_coronal_direction_world` | Return the coronal/platform direction of the embedded implant. |
| 352 | `_rebuild_emergence_controller_geometry` | Rebuild one controller as the clean v7.0.53 cylinder, preserving pose. |
| 448 | `create_implant_emergence_tube` |  |
| 484 | `get_nearest_implant_to_point` | Devuelve el implante DSG cuyo sleeve queda más cerca de un punto world. |
| 522 | `ensure_implant_divergence_property` |  |
| 539 | `copy_implant_world_rotation_keep_position` | Copia el eje del maestro y aplica una divergencia individual controlada. |
| 573 | `is_implant_parallel_locked` | True when an implant must keep its current pose during parallelization. |
| 588 | `set_implant_parallel_locked` |  |
| 600 | `get_implant_for_parallel_lock` | Resolve the implant the lock button should affect. |
| 613 | `get_parallel_master_implant` | Devuelve el implante maestro elegido en UI o el activo/seleccionado. |
| 628 | `get_next_implant_name` |  |
| 641 | `get_implant_center_world` |  |
| 648 | `get_implant_axis_world` |  |
| 655 | `get_implant_length_world` | Length real aproximada del implante en world-space. |
| 675 | `get_sleeve_occlusal_sign` | Devuelve el lado del eje del implante donde debe ir el sleeve. |
| 707 | `get_sleeve_matrix_world` | Matriz clínica real del sleeve asociado a un implante. |
| 742 | `get_sleeve_center_world` |  |
| 746 | `get_sleeve_axis_world` |  |
| 754 | `_irrigation_entry_for_implant` |  |
| 762 | `build_frangible_irrigation_seal_object` | Build a selective irrigation membrane with engraved target marks. |
| 807 | `build_frangible_irrigation_seal_object._make_local_cylinder` |  |
| 833 | `build_frangible_irrigation_seal_object._make_local_box` |  |
| 936 | `build_export_frangible_irrigation_seals` |  |
| 977 | class `_IrrigationPropsOverlay` | Vista de propiedades que conserva los valores propios de un conducto. |
| 979 | `_IrrigationPropsOverlay.__init__` |  |
| 983 | `_IrrigationPropsOverlay.__getattr__` |  |
| 989 | `capture_irrigation_parameters` |  |
| 1010 | `irrigation_props_overlay` |  |
| 1019 | `irrigation_parameters_from_object` |  |
| 1032 | `store_irrigation_path` |  |
| 1055 | `load_irrigation_path_entries` |  |
| 1111 | `sort_irrigation_entries_for_boolean` | Links first, then regular channels, preserving relative order. |
| 1125 | `extend_polyline_ends` | Extiende una polilínea por sus extremos siguiendo la dirección del |
| 1148 | `smooth_polyline_chaikin` |  |
| 1165 | `_remove_near_duplicate_points` | Elimina duplicados consecutivos sin cambiar la intención clínica del usuario. |
| 1186 | `_angle_between_segments` | Ángulo en b entre a-b-c. Devuelve 0 si los segmentos son inválidos. |
| 1198 | `_centripetal_t` | Parámetro t para Catmull-Rom centrípeto. |
| 1207 | `_lerp_by_t` |  |
| 1214 | `catmull_rom_centripetal_point` | Punto Catmull-Rom centrípeto entre p1 y p2. |
| 1237 | `build_catmull_rom_frame_path` | Convierte los puntos manuales del contorno en una ruta densa y orgánica. |
| 1315 | `_frame_sparse_catmull_controls` | Reduce a dense geodesic polyline to a clean Catmull control polygon. |
| 1350 | `_frame_project_smoothed_catmull_to_surface` | Project Catmull samples back to the passive surface without large jumps. |
| 1394 | `_frame_clean_catmull_surface_loop` | Create the final clean surface-following loop from sparse Catmull controls. |
| 1418 | `_frame_surface_cache_key` |  |
| 1428 | `_build_frame_surface_graph_cache` | Build a compact mesh-edge graph for true geodesic routing. |
| 1577 | `_frame_nearest_vertex` |  |
| 1585 | `_frame_vertices_within_surface_radius` | Return nearby graph vertices ordered by geodesic edge distance. |
| 1624 | `_frame_anchor_width_profile` | Endpoint width test using the same 75/25 support policy. |
| 1699 | `_frame_resolve_safe_anchor` | Resolve a semantic contour click to the closest width-valid surface vertex. |
| 1790 | `_frame_np_distance` |  |
| 1797 | `_frame_local_vertex_mask` | Bounding corridor used only to limit work, never as route cost. |
| 1811 | `_frame_bidirectional_dijkstra` | Shortest path by accumulated physical mesh-edge length only. |
| 1847 | `_frame_bidirectional_dijkstra.relax_one` |  |
| 1920 | `_frame_scipy_dijkstra` | Exact shortest path on the mesh-edge CSR graph using SciPy C code. |
| 2046 | `_frame_exact_dijkstra` | Use compiled CSR Dijkstra first; retain an exact Python fallback. |
| 2072 | `_frame_geodesic_surface_route` | Adaptive exact Dijkstra constrained to the dental surface. |
| 2143 | `_frame_width_surface_bvh` | Lazy BVH used only by the hard full-width gate. |
| 2169 | `_frame_barycentric` |  |
| 2191 | `_frame_surface_projection` | Project a point to the evaluated surface without snapping it to a vertex. |
| 2264 | `_frame_ray_surface_height` | Height of the same surface sheet along the local normal line. |
| 2314 | `_frame_point_support_profile` | Cross-section retention of the tube at one continuous surface point. |
| 2384 | `_frame_resolve_continuous_anchor` | Resolve a semantic contour click to an exact face/barycentric anchor. |
| 2465 | `_frame_semantic_segment_seeds` |  |
| 2487 | `_frame_intrinsic_distance_field` |  |
| 2506 | `_frame_corridor_clearance_field` |  |
| 2543 | `_frame_continuous_project_and_smooth` |  |
| 2607 | `_frame_continuous_sweep_profile` |  |
| 2659 | `_frame_semantic_clearance_surface_route` | Plan one frame segment entirely on the IOS surface. |

## [_guide_parts/03_blockout_frame_geometry_c.py](../_guide_parts/03_blockout_frame_geometry_c.py)

2677 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `_frame_width_nearest_surface` |  |
| 21 | `_frame_width_tangent_and_lateral` | Stable local frame for width validation on a graph-geodesic route. |
| 85 | `_frame_width_retained_ratio` |  |
| 90 | `_frame_width_sample_is_hard_failure` |  |
| 95 | `_frame_route_full_width_profile` | Validate a geodesic while allowing only the outer 25% to embed. |
| 229 | `_frame_forbid_width_bottlenecks` | Dilate rejected bottlenecks so Dijkstra must go around/above them. |
| 309 | `_frame_width_preserving_surface_route` | Shortest intrinsic route preserving the mandatory central 75% band. |
| 429 | `_frame_intrinsic_resample` | Resample along the mesh-edge polyline; never project through free space. |
| 463 | `_frame_virtual_anchor_shortest_route` | Shortest surface route between exact face/barycentric endpoints. |
| 559 | `_frame_component_labels` | Connected-component label per surface vertex (cached), or None. |
| 576 | `_frame_preferred_component` | Component the frame must follow on a joined passive model. |
| 597 | `_frame_anchor_on_component` | Nearest vertex of ``component`` as a routing anchor. |
| 613 | `build_surface_intrinsic_frame_path` | Shortest on-surface closed frame through user anchors in click order. |
| 816 | `create_poly_curve_object` | Lightweight POLY sweep: no Bézier handles and therefore no overshoot. |
| 847 | `_frame_organic_bezier_controls` | Return a clean control polygon for the visible frame tube. |
| 886 | `build_surface_poly_tube_mesh` |  |
| 892 | `_clamp_vector_length` | Limita una tangente sin cambiar su dirección. |
| 901 | `_tcb_value` | Lee TCB dentro de rangos estables para trayectorias clínicas. |
| 923 | `_kochanek_bartels_tangent_pairs` | Tangentes entrantes/salientes TCB para una ruta abierta. |
| 1004 | `_hermite_tcb_point` | Evalúa un segmento Hermite equivalente a un segmento Bezier TCB. |
| 1016 | `build_kochanek_bartels_path` | Ruta abierta densa que atraviesa todos los anchors usando TCB. |
| 1057 | `_ordered_points_from_evaluated_curve` | Extrae la polilínea evaluada de un Curve Path abierto en orden topológico. |
| 1106 | `build_hooked_tcb_path` | Construye un Bezier Path real, fija contactos con Hook y devuelve su eje. |
| 1229 | `simplify_points_by_distance` |  |
| 1241 | `project_point_to_line` |  |
| 1249 | `get_sleeve_entry_data` |  |
| 1275 | `get_irrigation_taper_length` | Length de la reducción progresiva del canal interno. |
| 1291 | `get_sleeve_wall_geometry` | Geometría radial real de la pared del sleeve para irrigación. |
| 1351 | `build_irrigation_outer_path` | Trayectoria exterior imperativa del tubo de irrigación. |
| 1419 | `get_irrigation_funnel_geometry` | Geometría del lumen con penetración radial imperativa. |
| 1489 | `_irrigation_outward_centerline` | Devuelve la línea central externa desde el sleeve hacia fuera. |
| 1542 | `build_irrigation_lumen_path` | Trayectoria del canal interno centrada en el tubo exterior. |
| 1550 | `_smootherstep01` | Interpolación aún más orgánica para cambios de diámetro. |
| 1556 | `_append_sample` | Añade una muestra de barrido evitando duplicados exactos. |
| 1570 | `_build_transport_frames` | Frames de rotación mínima para barridos tubulares. |
| 1647 | `append_variable_radius_tube_to_bmesh` | Añade un tubo continuo de radio variable en coordenadas mundo. |
| 1708 | `_resample_polyline_with_distances` | Remuestrea una polilínea manteniendo distancia acumulada. |
| 1731 | `build_irrigation_funnel_samples` | Muestras del lumen de irrigación como UN SOLO tubo tapered. |
| 1797 | `build_variable_radius_tube_object` | Crea un objeto mesh cerrado desde muestras de centro/radio. |
| 1857 | `build_irrigation_complete_lumen_cutter` | Cutter único tapered: salida fina → reducción progresiva → canal. |
| 1874 | `build_irrigation_constant_lumen_samples` | Muestras de lumen de radio constante para el modo sin embudo. |
| 1900 | `create_bezier_curve_object` |  |
| 1936 | `convert_curve_to_mesh` |  |
| 1950 | `_distance_along_polyline_to_nearest_point` | Distancia acumulada aproximada hasta el punto de la ruta más cercano. |
| 1969 | `build_organic_tube_mesh` |  |
| 1990 | `get_irrigation_junction_outer_radius` | Radio del cuello que realmente atraviesa la pared lateral del sleeve. |
| 2018 | `build_irrigation_radial_collar` | Crea un collar cónico radial robusto entre el sleeve y el tubo. |
| 2128 | `apply_difference_exact_transactional` | Aplica DIFFERENCE EXACT con rollback local y diagnóstico manifold. |
| 2166 | `force_voxel_union_imperative` | Fusión forzada: Join de shells + Voxel Remesh fino. |
| 2218 | `build_pristine_sleeve_shell` | Reconstruye el cilindro hueco exacto del sleeve asociado. |
| 2250 | `build_sleeve_plane_trim_cutter` | Cilindro tipo semiespacio que vuelve a cortar una cara plana del sleeve. |
| 2276 | `build_sleeve_lumen_restore_cutter` | Reabre el lumen axial exacto después de la fusión imperativa. |
| 2290 | `restore_sleeve_after_imperative_irrigation` | Restaura shell, planos superior/inferior y lumen sin cancelar el tubo. |
| 2338 | `fuse_irrigation_staged_exact` | Fusión imperativa del tubo hasta el interior del lumen. |
| 2421 | `get_contour_curve` |  |
| 2426 | `ensure_contour_curve` |  |
| 2444 | `set_contour_curve_points` |  |
| 2461 | `get_contour_curve_points` |  |
| 2469 | `clear_contour_curve` | Elimina el objeto temporal del contorno y, si queda huérfano, su datablock Curve. |
| 2493 | `consume_contour_after_frame` | Limpia todo el estado de contorno solo tras crear el frame con éxito. |
| 2508 | `sync_legacy_contour_points` | Mantiene compatibilidad al abrir el archivo con versiones anteriores. |
| 2515 | `_mark_gpu_dirty` | Compatibilidad con operadores modales: el dibujo GPU ya no cachea batches. |
| 2520 | `_as_gpu_coords` |  |
| 2524 | `draw_polyline_gpu` | Dibuja puntos y polilínea 3D con una sola rutina GPU. |
| 2549 | `_draw_callback_contour` |  |
| 2570 | `register_contour_draw_handler` |  |
| 2577 | `unregister_contour_draw_handler` |  |
| 2591 | `_draw_callback_irrigation` |  |
| 2610 | `register_irr_draw_handler` |  |
| 2617 | `unregister_irr_draw_handler` |  |
| 2635 | `_engrave_preview_refresh_timer` |  |
| 2654 | `_on_engrave_setting_change` | Mark the engraving preview as stale without recomputing it live. |

## [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py)

4446 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | class `DSG_ContourPoint` |  |
| 4 | `_irrigation_sleeve_channel_items` | Language-aware labels for the irrigation channel mode dropdown. |
| 34 | `_retention_cache_key` |  |
| 81 | `_clear_retention_geometry_cache` |  |
| 85 | `_tag_dsg_view3d_redraw` |  |
| 97 | `_on_retention_level_change` | Keep profile changes lightweight; the explicit preset buttons rebuild. |
| 105 | `_on_retention_percent_change` |  |
| 116 | class `DSG_Props` |  |
| 611 | `get_view_ray` |  |
| 622 | `intersect_ray_plane` |  |
| 635 | `point_in_view_plane` |  |
| 651 | `_raycast_local_safe` | Raycast tolerante a objetos sin malla evaluada. |
| 750 | `do_raycast_detailed` |  |
| 781 | `do_raycast` |  |
| 790 | `_event_view_ray` | Return a world-space ray for the WINDOW region under the mouse. |
| 832 | `_raycast_object_from_world_ray` |  |
| 857 | `_nearest_visible_raycast` |  |
| 879 | `_nearest_implant_vertex` | Snap a clicked implant surface point to the nearest real mesh vertex. |
| 899 | `_dsg_data_access_ready` | Return True only when Blender has restored normal blend-data access. |
| 915 | `_dicom_measurement_roots` |  |
| 925 | `_dicom_measurement_roots.sort_key` |  |
| 933 | `_next_dicom_measurement_index` |  |
| 943 | `_ensure_dicom_measure_material` |  |
| 955 | `_assign_single_material` |  |
| 963 | `_create_dicom_measure_marker` |  |
| 979 | `_create_dicom_measure_line` |  |
| 1002 | `_set_dicom_measurements_visibility` | Show or hide all DICOM two-point measurement visuals. |
| 1040 | `_dicom_measurement_points` |  |
| 1070 | `_update_one_dicom_measurement` |  |
| 1105 | `_tag_dicom_measurement_redraw` |  |
| 1118 | `_update_all_dicom_measurements` |  |
| 1135 | `_dsg_dicom_measurement_update_timer` |  |
| 1145 | `_dsg_update_dicom_measurements_handler` |  |
| 1165 | `_remove_dicom_measure_handler` |  |
| 1180 | `_register_dicom_measure_handler` |  |
| 1189 | `_remove_dicom_measurement_root` |  |
| 1207 | `_clear_all_dicom_measurements` |  |
| 1228 | `_remove_dicom_measurements_for_implant` |  |
| 1240 | `_create_dicom_measurement` |  |
| 1270 | `_create_dicom_mpr_measurement` |  |
| 1304 | class `DSG_OT_MeasureImplantToDICOM` | `dsg.measure_implant_to_dicom` · Measure Implant to DICOM |
| 1317 | `DSG_OT_MeasureImplantToDICOM.poll` |  |
| 1327 | `DSG_OT_MeasureImplantToDICOM.invoke` |  |
| 1342 | `DSG_OT_MeasureImplantToDICOM.modal` |  |
| 1433 | `DSG_OT_MeasureImplantToDICOM._finish_cursor` |  |
| 1442 | class `DSG_OT_MeasureDICOMTwoPoints` | `dsg.measure_dicom_two_points` · Measure Two Points in DICOM MPR |
| 1454 | `DSG_OT_MeasureDICOMTwoPoints.poll` |  |
| 1463 | `DSG_OT_MeasureDICOMTwoPoints.invoke` |  |
| 1477 | `DSG_OT_MeasureDICOMTwoPoints.modal` |  |
| 1540 | `DSG_OT_MeasureDICOMTwoPoints._finish_cursor` |  |
| 1547 | class `DSG_OT_RemoveLastDICOMMeasurement` | `dsg.remove_last_dicom_measurement` · Delete Last DICOM Measurement |
| 1552 | `DSG_OT_RemoveLastDICOMMeasurement.execute` |  |
| 1562 | class `DSG_OT_ClearDICOMMeasurements` | `dsg.clear_dicom_measurements` · Clear DICOM Measurements |
| 1567 | `DSG_OT_ClearDICOMMeasurements.execute` |  |
| 1581 | `get_active_guide_obj` | Recupera la guía de forma estrictamente read-only. |
| 1598 | `_normalized_or_fallback` |  |
| 1605 | `build_engrave_orientation_matrix` | Crea una matriz mundo para colocar texto tangente a la superficie. |
| 1639 | `_get_view_right_axis` | Usa el eje horizontal de la vista como fallback de orientación. |
| 1655 | `_get_view_up_axis` | Devuelve el eje vertical de la vista proyectado sobre la superficie. |
| 1669 | `get_nearest_implant_to_world_point` | Implant cuyo sleeve clínico queda más cerca de un punto del grabado. |
| 1691 | `get_engrave_x_axis_perpendicular_to_sleeve_base` | Orienta el texto con el eje de inserción capturado desde la vista. |
| 1747 | `update_engrave_axis_from_sleeve_base` | Recalcula y guarda la orientación del grabado según el eje de inserción. |
| 1756 | `create_or_update_engrave_anchor` |  |
| 1771 | `get_engrave_basis` | Devuelve ejes ortonormales del grabado: X lectura, Y alto, Z exterior. |
| 1793 | `raycast_object_along_world` | Raycast mundo→objeto usando el mismo fallback seguro del selector modal. |
| 1826 | `project_flat_engrave_mesh_to_plane` | Remapea el texto a un cutter plano rápido, sin raycast por vértice. |
| 1873 | `_engrave_raycast_bvh` | Raycast rápido con un BVHTree ya construido para no evaluar la guía por vértice. |
| 1904 | `_engrave_projection_signature` | Stable key for reusing the preview's curved surface projection. |
| 1929 | `_store_engrave_projection_cache` |  |
| 1947 | `_load_engrave_projection_cache` |  |
| 1957 | `project_engrave_mesh_to_guide_curvature` | Adapta una malla de texto a la curvatura local de DSG_Guide. |
| 2081 | `create_engrave_text_mesh_object` | Crea el grabado con la biblioteca interna low-poly de DSG. |
| 2110 | `create_or_update_engrave_preview` | Muestra una previsualización curva no destructiva del texto en la superficie. |
| 2145 | `create_engrave_text_cutter` | Crea un texto sólido para recortar la guía con Boolean Difference. |
| 2194 | `_remove_modifier_if_present` |  |
| 2203 | `_engrave_boolean_result_plausible` | Cheap validation for a shallow local engraving cut. |
| 2223 | `apply_patient_engrave_transactional` | FAST-first local engraving with exact transactional fallbacks. |
| 2296 | `raycast_sleeve_lateral_on_guide` | Identifica el sleeve mediante raycast, pero no permite usar su caras planas. |
| 2376 | class `DSG_OT_RunBooleanPreflight` | `dsg.run_boolean_preflight` · Check / Repair Meshes |
| 2383 | `DSG_OT_RunBooleanPreflight.execute` |  |
| 2460 | class `DSG_OT_ForceOrthographicView` | `dsg.force_orthographic_view` · Restore Orthographic Precision View |
| 2466 | `DSG_OT_ForceOrthographicView.execute` |  |
| 2477 | class `DSG_OT_Reset` | `dsg.reset` · Reset Workflow |
| 2483 | `DSG_OT_Reset.invoke` |  |
| 2486 | `DSG_OT_Reset.execute` |  |
| 2521 | `DSG_OT_Reset.execute.collect_collection_objects` |  |
| 2644 | class `DSG_OT_ResetCurrentStep` | `dsg.reset_current_step` · Back One Clinical Step |
| 2651 | `DSG_OT_ResetCurrentStep.poll` |  |
| 2655 | `DSG_OT_ResetCurrentStep._return_to_alignment` | Restore the alignment review without deleting DSG geometry. |
| 2734 | `DSG_OT_ResetCurrentStep.execute` |  |
| 2814 | class `DSG_OT_UseSelectedIOSModel` | `dsg.use_selected_ios_model` · Use Selected IOS Model |
| 2821 | `DSG_OT_UseSelectedIOSModel.poll` |  |
| 2830 | `DSG_OT_UseSelectedIOSModel.execute` |  |
| 2862 | class `DSG_OT_PrepareAlignedModel` | `dsg.prepare_aligned_model` · Choose Insertion Axis from View |
| 2868 | `DSG_OT_PrepareAlignedModel.execute` |  |
| 2922 | class `DSG_OT_ConfirmModel` | `dsg.confirm_model` · Confirm Model |
| 2927 | `DSG_OT_ConfirmModel.execute` |  |
| 2946 | class `DSG_OT_CaptureAxis` | `dsg.capture_axis` · Capture Axis from View |
| 2951 | `DSG_OT_CaptureAxis.execute` |  |
| 2986 | class `DSG_OT_SelectAxis` | `dsg.select_axis` · Select Axis |
| 2991 | `DSG_OT_SelectAxis.execute` |  |
| 2997 | class `DSG_OT_ConfirmAxis` | `dsg.confirm_axis` · Confirm Axis |
| 3002 | `DSG_OT_ConfirmAxis.execute` |  |
| 3012 | class `DSG_OT_SelectRetentionPreset` | `dsg.select_retention_preset` · Select Retention Profile |
| 3022 | `DSG_OT_SelectRetentionPreset.execute` |  |
| 3053 | `_set_blockout_ui_busy` | Show immediate visual feedback while the synchronous geometry stage runs. |
| 3071 | `_blockout_stats_summary` |  |
| 3088 | `_blockout_percentile` | Small dependency-free percentile helper for blockout diagnostics. |
| 3102 | `_validate_blockout_seating` | Audit a view-raycast blockout before it can become a cutter. |
| 3221 | `_store_blockout_seating_report` | Persist a concise audit result on both the candidate and scene props. |
| 3248 | `_generate_view_raycast_blockout_transaction` | Build a candidate first and replace the valid blockout only after success. |
| 3335 | `build_blockout_simple_fast` | Compatibility entry point: the only active blockout is the view-parallel BVH raycast. |
| 3346 | class `DSG_OT_GenerateBlockout` | `dsg.generate_blockout` · Generate Blockout |
| 3351 | `DSG_OT_GenerateBlockout.execute` |  |
| 3413 | class `DSG_OT_AnalyzeRetention` | `dsg.analyze_retention` · Analyze Coronary Perimeter |
| 3419 | `DSG_OT_AnalyzeRetention.execute` |  |
| 3423 | class `DSG_OT_ValidateBlockoutSeating` | `dsg.validate_blockout_seating` · Validate Guide Seating |
| 3430 | `DSG_OT_ValidateBlockoutSeating.execute` |  |
| 3463 | class `DSG_OT_ApplySelectedBlockoutRelief` | `dsg.apply_selected_blockout_relief` · Apply Selected Local Relief |
| 3471 | `DSG_OT_ApplySelectedBlockoutRelief.poll` |  |
| 3478 | `DSG_OT_ApplySelectedBlockoutRelief.execute` |  |
| 3506 | class `DSG_OT_AutoPrepareRetention` | `dsg.auto_prepare_retention` · Prepare Model |
| 3514 | `DSG_OT_AutoPrepareRetention.execute` |  |
| 3518 | class `DSG_OT_ConfirmBlockout` | `dsg.confirm_blockout` · Confirm Blockout |
| 3528 | `DSG_OT_ConfirmBlockout.execute` |  |
| 3665 | class `DSG_OT_ForceConfirmBlockout` | `dsg.force_confirm_blockout` · Continue After Manual Seating Review |
| 3672 | `DSG_OT_ForceConfirmBlockout.invoke` |  |
| 3675 | `DSG_OT_ForceConfirmBlockout.execute` |  |
| 3679 | class `DSG_OT_StartDrawing` | `dsg.start_drawing` · Draw / Continue Outline |
| 3686 | `DSG_OT_StartDrawing._is_view_navigation_event` | Let Blender's native viewport navigation run during point placement. |
| 3711 | `DSG_OT_StartDrawing.modal` |  |
| 3762 | `DSG_OT_StartDrawing.invoke` |  |
| 3797 | class `DSG_OT_ToggleContourPointEdit` | `dsg.toggle_contour_point_edit` · Edit Frame Points |
| 3803 | `DSG_OT_ToggleContourPointEdit.execute` |  |
| 3842 | class `DSG_OT_ClearContour` | `dsg.clear_contour` · Clear Outline |
| 3847 | `DSG_OT_ClearContour.execute` |  |
| 3856 | class `DSG_OT_ConfirmContour` | `dsg.confirm_contour` · Confirm Outline |
| 3861 | `DSG_OT_ConfirmContour.execute` |  |
| 3892 | class `DSG_OT_CreateImplant` | `dsg.create_implant` · Create Implant |
| 3897 | `DSG_OT_CreateImplant.execute` |  |
| 4053 | class `DSG_OT_RemoveLastImplant` | `dsg.remove_last_implant` · Delete Last Implant |
| 4058 | `DSG_OT_RemoveLastImplant.execute` |  |
| 4090 | class `DSG_OT_ToggleImplantParallelLock` | `dsg.toggle_implant_parallel_lock` · Lock Implant for Parallelization |
| 4098 | `DSG_OT_ToggleImplantParallelLock.execute` |  |
| 4126 | class `DSG_OT_SetParallelMaster` | `dsg.set_parallel_master` · Use Selected as Master |
| 4131 | `DSG_OT_SetParallelMaster.execute` |  |
| 4146 | class `DSG_OT_ParallelizeImplants` | `dsg.parallelize_implants` · Parallelize Implants to Master |
| 4151 | `DSG_OT_ParallelizeImplants.execute` |  |
| 4206 | class `DSG_OT_CreateImplantEmergenceTubes` | `dsg.create_implant_emergence_tubes` · Create Implant Emergence Tubes |
| 4214 | `DSG_OT_CreateImplantEmergenceTubes.execute` |  |
| 4281 | class `DSG_OT_ConfirmImplant` | `dsg.confirm_implant` · Confirm Implants |
| 4286 | `DSG_OT_ConfirmImplant.execute` |  |

## [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py)

3691 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | class `DSG_OT_BuildTubeFrame` | `dsg.build_tube_frame` · Generate Tubular Frame |
| 6 | `DSG_OT_BuildTubeFrame.execute` |  |
| 186 | `get_pending_microscrew_preview` |  |
| 207 | `get_confirmed_microscrew_objects` |  |
| 223 | `get_microscrew_records` |  |
| 233 | `set_microscrew_records` |  |
| 237 | `_record_from_microscrew_object` |  |
| 266 | `_matrix_along_local_z` |  |
| 275 | `_create_cylinder_between` |  |
| 292 | `make_microscrew_anatomic_sleeve_mesh` | Closed sleeve whose lumen and anatomical seat follow screw diameter. |
| 369 | `_smart_anchor_tangent_basis` |  |
| 386 | `_smart_anchor_project_candidate` |  |
| 429 | `_smart_anchor_neighbor_direction` |  |
| 446 | `_smart_anchor_local_roughness` |  |
| 474 | `_smart_anchor_fit_metrics` |  |
| 500 | `_smart_anchor_probe_solid_interior` | Detecta qué lado de la superficie entra realmente en el sólido actual. |
| 558 | `_smart_anchor_single_wall_thickness` | Mide el grosor del sólido prebooleana y orienta su lado interior real. |
| 568 | `_smart_anchor_structural_metrics` | Devuelve grosor débil robusto y profundidad segura de enterramiento. |
| 639 | `_smart_anchor_candidate_score` |  |
| 690 | `_smart_anchor_generate_candidates` |  |
| 797 | `_smart_anchor_pair_score` |  |
| 826 | `_smart_anchor_optimize_pair` |  |
| 888 | `_optimize_reinforcement_chain_anchors` |  |
| 946 | `_fixed_reinforcement_anchor_burials` | Mantiene exactamente los puntos elegidos y calcula solo su solape interno. |
| 986 | `_smooth_circular_scalars` |  |
| 1003 | `_support_surface_under_candidate` | Comprueba si el candidato está situado sobre alguna cara del soporte. |
| 1030 | `_maximum_supported_offset_scale` | Mayor fracción del offset cuya proyección sigue dentro del frame. |
| 1064 | `_all_footprint_points_supported` | Comprueba el aro completo conservando exactamente su forma nominal. |
| 1080 | `_maximum_round_footprint_scale` | Mayor escala uniforme que mantiene toda la huella dentro del soporte. |
| 1117 | `_adaptive_volcano_footprint_offsets` | Huella volcánica grande, redonda y contenida mediante escala uniforme. |
| 1149 | `_cubic_bezier_tangent` |  |
| 1157 | `_microscrew_support_radius_at` | Conector grueso con apoyo amplio en frame y cuello seguro en el sleeve. |
| 1183 | `make_microscrew_smooth_support_mesh` | Connector Bézier curvo, cerrado y con tapas enterradas en los solapes. |
| 1285 | `_microscrew_target_candidates` |  |
| 1301 | `raycast_microscrew_target` | Busca el segundo punto en modelo/blockout; usa el frame como fallback. |
| 1307 | `raycast_microscrew_target.best_hit` |  |
| 1330 | `build_microscrew_preview` |  |
| 1488 | class `DSG_OT_StartMicroscrew` | `dsg.start_microscrew` · Select 3 Microscrew Points |
| 1493 | `DSG_OT_StartMicroscrew._marker_name` |  |
| 1496 | `DSG_OT_StartMicroscrew._add_marker` |  |
| 1505 | `DSG_OT_StartMicroscrew._remove_marker` |  |
| 1510 | `DSG_OT_StartMicroscrew._finish` |  |
| 1515 | `DSG_OT_StartMicroscrew.modal` |  |
| 1584 | `DSG_OT_StartMicroscrew.invoke` |  |
| 1610 | `_microscrew_preview_visual_object` | Devuelve el STL visual editable del microtornillo pendiente. |
| 1641 | `_microscrew_axis_from_visual_or_preview` | Extrae el eje actual del microtornillo. |
| 1663 | `update_pending_microscrew_from_visual` | Recrea el preview usando el microtornillo visual como nuevo punto 2. |
| 1723 | class `DSG_OT_UpdateMicroscrewFromVisual` | `dsg.update_microscrew_from_visual` · Update Microscrew From Visual |
| 1728 | `DSG_OT_UpdateMicroscrewFromVisual.execute` |  |
| 1743 | `confirm_pending_microscrew_object` | Convierte el preview pendiente en microtornillo confirmado. |
| 1810 | class `DSG_OT_ConfirmMicroscrewPreview` | `dsg.confirm_microscrew_preview` · Confirm Microscrew |
| 1815 | `DSG_OT_ConfirmMicroscrewPreview.execute` |  |
| 1827 | class `DSG_OT_CancelMicroscrewPreview` | `dsg.cancel_microscrew_preview` · Discard Pending Microscrew |
| 1832 | `DSG_OT_CancelMicroscrewPreview.execute` |  |
| 1846 | class `DSG_OT_RemoveLastMicroscrew` | `dsg.remove_last_microscrew` · Delete Last Microscrew |
| 1851 | `DSG_OT_RemoveLastMicroscrew.execute` |  |
| 1886 | class `DSG_OT_ApplyMicroscrewsToFrame` | `dsg.apply_microscrews_to_frame` · Add Microscrews to Frame |
| 1891 | `DSG_OT_ApplyMicroscrewsToFrame.execute` |  |
| 1968 | class `DSG_OT_CreateAnimatedMicroscrews` | `dsg.create_animated_microscrews` · Create Animated Screws |
| 1973 | `DSG_OT_CreateAnimatedMicroscrews.execute` |  |
| 2029 | class `DSG_OT_PlayAnimatedMicroscrews` | `dsg.play_animated_microscrews` · Play Microscrew Insertion |
| 2033 | `DSG_OT_PlayAnimatedMicroscrews.execute` |  |
| 2065 | class `DSG_OT_StopAnimatedMicroscrews` | `dsg.stop_animated_microscrews` · Stop Microscrew Animation |
| 2069 | `DSG_OT_StopAnimatedMicroscrews.execute` |  |
| 2092 | class `DSG_OT_ToggleAnimatedMicroscrewsVisibility` | `dsg.toggle_animated_microscrews_visibility` · Show or Hide Animated Microscrews |
| 2096 | `DSG_OT_ToggleAnimatedMicroscrewsVisibility.execute` |  |
| 2119 | class `DSG_OT_ShowAnimatedMicroscrewStart` | `dsg.show_animated_microscrew_start` · Show Microscrew Start Position |
| 2123 | `DSG_OT_ShowAnimatedMicroscrewStart.execute` |  |
| 2137 | class `DSG_OT_ShowAnimatedMicroscrewStop` | `dsg.show_animated_microscrew_stop` · Show Microscrew Final Seat |
| 2141 | `DSG_OT_ShowAnimatedMicroscrewStop.execute` |  |
| 2157 | class `DSG_OT_ConfirmTubeFrame` | `dsg.confirm_tube_frame` · Confirm Frame |
| 2162 | `DSG_OT_ConfirmTubeFrame.execute` |  |
| 2206 | `get_sleeve_preview_objects` |  |
| 2218 | `_archive_current_guide_for_sleeve_rebuild` | Aparta la guía actual sin destruir IDs durante una regeneración. |
| 2251 | `_recover_frame_source_for_sleeve_rebuild` | Devuelve el frame clínico aunque ya se hubiera aplicado una guía. |
| 2274 | class `DSG_OT_ToggleLateralOpening` | `dsg.toggle_lateral_opening` · Lateral Opening (moved) |
| 2280 | `DSG_OT_ToggleLateralOpening.execute` |  |
| 2301 | class `DSG_OT_CaptureLateralOpeningView` | `dsg.capture_lateral_opening_view` · Use Current View for Post-Irrigation Opening |
| 2307 | `DSG_OT_CaptureLateralOpeningView.execute` |  |
| 2329 | `_lateral_window_manual_angle_map` | Return the per-implant manual window angles saved in Scene properties. |
| 2346 | `_store_lateral_window_manual_angle_map` |  |
| 2357 | `_remove_lateral_window_pick_markers` |  |
| 2370 | `_clear_lateral_window_manual_picks` |  |
| 2381 | `_lateral_window_manual_selection_status` |  |
| 2389 | `_create_lateral_window_pick_marker` | Create a tiny non-destructive arrow showing the user's chosen drill-entry side. |
| 2422 | `_signed_angle_delta` |  |
| 2426 | `_resolve_user_lateral_window_for_implant` | Validate the exact user-picked side, keeping irrigation geometry protected. |
| 2510 | class `DSG_OT_PickLateralOpeningSide` | `dsg.pick_lateral_opening_side` · Pick Lateral Opening Side |
| 2516 | `DSG_OT_PickLateralOpeningSide._restore_cursor` |  |
| 2522 | `DSG_OT_PickLateralOpeningSide.invoke` |  |
| 2548 | `DSG_OT_PickLateralOpeningSide.modal` |  |
| 2603 | class `DSG_OT_AddSleeve` | `dsg.add_sleeve` · Sleeve Preview |
| 2608 | `DSG_OT_AddSleeve.execute` |  |
| 2755 | class `DSG_OT_CreateApplySleeves` | `dsg.create_apply_sleeves` · Create and Apply Sleeves |
| 2760 | `DSG_OT_CreateApplySleeves.execute` |  |
| 2799 | class `DSG_OT_RebuildLateralWindowFromIrrigation` | `dsg.rebuild_lateral_window_from_irrigation` · Legacy Lateral Window Rebuild (disabled) |
| 2805 | `DSG_OT_RebuildLateralWindowFromIrrigation.execute` |  |
| 2813 | `_build_post_irrigation_lateral_opening_cutter` | One batch cutter for sleeve + frame, sized to the INNER sleeve diameter. |
| 2919 | class `DSG_OT_ApplyPostIrrigationLateralOpening` | `dsg.apply_post_irrigation_lateral_opening` · Apply Post-Irrigation Lateral Opening |
| 2924 | `DSG_OT_ApplyPostIrrigationLateralOpening.execute` |  |
| 3022 | class `DSG_OT_ContinueAfterIrrigation` | `dsg.continue_after_irrigation` · Continue After Irrigation |
| 3027 | `DSG_OT_ContinueAfterIrrigation.execute` |  |
| 3052 | class `DSG_OT_ApplySleeves` | `dsg.apply_sleeves` · Apply Sleeves |
| 3057 | `DSG_OT_ApplySleeves.execute` | Crea DSG_Guide sin borrar objetos durante la evaluación del depsgraph. |
| 3239 | class `DSG_OT_ConfirmSleeve` | `dsg.confirm_sleeve` · Continue to Irrigation |
| 3250 | `DSG_OT_ConfirmSleeve.execute` |  |
| 3284 | class `DSG_OT_ProtectDrillInsertion` | `dsg.protect_drill_insertion` · Clear Drill Insertion Path |
| 3289 | `DSG_OT_ProtectDrillInsertion.execute` |  |
| 3305 | class `DSG_OT_AddDrillChannel` | `dsg.add_drill_channel` · Create Drill Channels |
| 3310 | `DSG_OT_AddDrillChannel.execute` | Perfora cada shell cerrado por separado y solo después reúne la guía. |
| 3391 | `DSG_OT_AddDrillChannel.execute.store_diagnostic` |  |
| 3593 | class `DSG_OT_PrepareAndCreateDrillChannels` | `dsg.prepare_and_create_drill_channels` · Prepare and Create Drill Channels |
| 3601 | `DSG_OT_PrepareAndCreateDrillChannels.execute` |  |
| 3648 | class `DSG_OT_ConfirmDrill` | `dsg.confirm_drill` · Confirm Channels → Final Boolean |
| 3653 | `DSG_OT_ConfirmDrill.execute` |  |

## [_guide_parts/06_irrigation_a.py](../_guide_parts/06_irrigation_a.py)

2878 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `get_confirmed_irrigation_walls` | Wall Thicknesses externas confirmadas que aún no se han combinado con DSG_Guide. |
| 17 | `_sample_irrigation_c_arc_points` | Samples a planar circular arc around the sleeve axis. |
| 44 | `_sample_plumbing_elbow_curve` | Returns a rounded plumbing-style elbow between two points. |
| 78 | `_continuous_irrigation_c_path` | Return one uninterrupted centreline for the complete C manifold. |
| 100 | `_continuous_irrigation_c_path.elbow` |  |
| 123 | `_continuous_irrigation_c_path.extend` |  |
| 139 | `_irrigation_c_continuity_samples` | Samples the intended C lumen centreline for post-Boolean auditing. |
| 156 | `_world_bvh_for_closed_mesh` | Build a world-space BVH and a conservative ray length for one mesh. |
| 192 | `_point_inside_closed_bvh` | Parity test with three non-axis-aligned rays to avoid edge ambiguity. |
| 222 | `_blocked_irrigation_c_samples` | Return C-centreline samples still occupied by solid after the cut. |
| 247 | `get_irrigation_internal_ring_geometry` | Sleeve manifold geometry using an open C instead of a closed annulus. |
| 340 | `build_irrigation_internal_ring_parts` | Build one continuous open-C cutter inside the sleeve. |
| 403 | `build_irrigation_c_only_cutter` | Build a compact cutter containing only the continuous sleeve C lumen. |
| 473 | `build_irrigation_initial_control_points` | Convierte los clics del usuario en controles del eje interno. |
| 519 | `smooth_irrigation_centerline_controls` | Suaviza solo la parte exterior y conserva el tramo radial del sleeve. |
| 552 | `_irrigation_polyline_sample` |  |
| 579 | `_quintic_zero_acceleration_point` | Quíntica con posición/tangente fijadas y aceleración cero en extremos. |
| 609 | `_build_irrigation_radial_exit_blend` | Sustituye el primer codo por una salida radial G1/C2 estable. |
| 672 | `build_irrigation_wall_path` | Ruta exterior con salida radial estable y giro separado del estrechamiento. |
| 724 | `build_irrigation_profile_samples` | Builds the irrigation lumen profile. |
| 786 | `build_irrigation_lumen_samples_from_controls` |  |
| 795 | `_smooth_monotonic_irrigation_radii` |  |
| 824 | `_monotone_cubic_scalar` |  |
| 836 | `_monotone_three_point_slopes` |  |
| 850 | `apply_irrigation_sleeve_volcano_to_outer_samples` | Perfil exterior único, monótono y desacoplado de la curvatura del eje. |
| 934 | `build_irrigation_outer_wall_object` |  |
| 968 | `build_irrigation_lumen_preview_object` |  |
| 989 | `get_irrigation_lumen_preview` |  |
| 1000 | `_ensure_irrigation_lumen_diagnostic_material` | Material transparente para ver exactamente el lumen interno comprobado. |
| 1040 | `get_irrigation_lumen_diagnostic_object` |  |
| 1061 | `remove_irrigation_lumen_diagnostics` | Elimina solo los objetos de diagnóstico del lumen, no la pared ni el canal. |
| 1083 | `create_irrigation_lumen_diagnostic_object` | Crea la geometría exacta que usa el preflight del lumen de agua. |
| 1165 | `build_pending_irrigation_lumen_diagnostic` |  |
| 1195 | `remove_irrigation_preview_bundle` |  |
| 1205 | `build_blended_irrigation_outer_tube_mesh` | Compatibilidad: ahora construye la pared desde los controles del eje interno. |
| 1213 | `build_irrigation_combined_lumen_cutter` | Un único cutter que atraviesa paredes externas y sleeves. |
| 1272 | `append_hollow_variable_radius_tube_to_bmesh` | Construye una pared hueca con radio exterior opcionalmente independiente. |
| 1360 | `apply_venturi_profile_to_samples` | Compatibility no-op: the common-trunk Venturi is intentionally disabled. |
| 1374 | `apply_balancing_nozzle_after_split` | Applies a smooth metering nozzle only inside a daughter branch. |
| 1414 | `apply_balancing_nozzle_after_split.radius_for_distance` |  |
| 1449 | `build_irrigation_junction_cutter` | Builds one fused cutter that opens a true Y junction in both closed walls. |
| 1485 | `_merge_irrigation_inner_outer_profiles` | Une perfiles coincidentes para construir lumen y exterior independientes. |
| 1509 | `build_irrigation_hollow_wall_object` | Builds a manifold hollow wall directly from the irrigation centerline. |
| 1581 | `_irrigation_entry_effective_props` |  |
| 1593 | `_fuse_irrigation_solids_with_voxel` |  |
| 1616 | `_entry_vector` |  |
| 1628 | `_sample_cubic_bezier_segment` |  |
| 1645 | `_midpoint_wye_metadata` | Returns the complete adaptive midpoint-manifold geometry. |
| 1722 | `_forced_wye_metadata` | Compatibility tuple used by older callers. |
| 1730 | `_deduplicate_radius_samples` |  |
| 1742 | `force_source_samples_into_balanced_wye` | Replaces the old straight source segment with a new midpoint Y. |
| 1821 | `reshape_link_samples_into_midpoint_wye` | Rebuilds the linked daughter up to the same calculated split center. |
| 1850 | `irrigation_branch_length_to_split` | Approximate sleeve-to-split centreline length for one daughter. |
| 1864 | `irrigation_branch_resistance_to_split` | Numerically estimates relative Hagen-Poiseuille resistance to the Y. |
| 1898 | `calculate_length_compensated_nozzles` | Minimum-loss passive balance for two daughter branches. |
| 2042 | `_add_forced_wye_plenum_part` | Adds a compact overlap chamber at the calculated midpoint split. |
| 2059 | `_calculate_midpoint_wye_balances` | Nozzle-free linked irrigation. |
| 2070 | `_apply_entry_midpoint_geometry` |  |
| 2079 | `_apply_entry_balancing` | Preserve the full lumen across source and linked branches. |
| 2084 | `build_irrigation_y_network_hollow_wall` | Builds a new adaptive manifold instead of preserving the old junction. |
| 2235 | `build_irrigation_y_network_lumen_cutter` | Creates a cutter that exactly follows the rebuilt manifold lumen. |
| 2297 | `remove_disconnected_islands_keep_largest` | Conserva el cuerpo principal y elimina shells desconectados. |
| 2318 | `remove_disconnected_islands_keep_largest.find` |  |
| 2324 | `remove_disconnected_islands_keep_largest.union` |  |
| 2401 | `split_mesh_object_loose_parts` | Separa shells desconectados sin Edit Mode ni bpy.ops.mesh.separate. |
| 2413 | `split_mesh_object_loose_parts.find` |  |
| 2419 | `split_mesh_object_loose_parts.union` |  |
| 2458 | `object_world_aabb` |  |
| 2470 | `aabb_overlap` |  |
| 2483 | `build_irrigation_single_lumen_cutter` |  |
| 2606 | `cleanup_boolean_result_minimal` | Limpieza topológica mínima después de una booleana. |
| 2641 | `make_offset_boolean_cutter` | Duplica y expande suavemente un cutter cerrado siguiendo sus normales. |
| 2690 | `apply_difference_exact_checked` | DIFFERENCE transaccional sobre un shell cerrado. |
| 2708 | `apply_difference_exact_checked.restore_fresh_original` |  |
| 2712 | `apply_difference_exact_checked.run_attempt` |  |
| 2862 | `get_pending_irrigation_preview` | Busca el preview pendiente sin escribir en Scene durante Panel.draw(). |

## [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py)

2860 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `create_irrigation_preview_path_curve` | Curva editable cuyos puntos son el eje interno real del conducto. |
| 33 | `get_irrigation_preview_curve` |  |
| 44 | `get_irrigation_preview_path_world` |  |
| 61 | class `DSG_OT_SetIrrigationCylinderChannelMode` | `dsg.set_irrigation_cylinder_channel_mode` · Set cylinder channel mode |
| 71 | `DSG_OT_SetIrrigationCylinderChannelMode.execute` |  |
| 94 | class `DSG_OT_ToggleIrrigationImplantSeal` | `dsg.toggle_irrigation_implant_seal` · Open / Seal Implant Irrigation |
| 102 | `DSG_OT_ToggleIrrigationImplantSeal.execute` |  |
| 125 | `build_irrigation_preview_from_points` | Build the same irrigation preview as the modal tool from explicit points. |
| 181 | class `DSG_OT_StartIrrigationFromPoints` | `dsg.start_irrigation_from_points` · Irrigation Preview from Points |
| 192 | `DSG_OT_StartIrrigationFromPoints.execute` |  |
| 218 | class `DSG_OT_StartIrrigation` | `dsg.start_irrigation` · Draw Irrigation Channel |
| 223 | `DSG_OT_StartIrrigation._finish_modal` |  |
| 229 | `DSG_OT_StartIrrigation.modal` |  |
| 285 | `DSG_OT_StartIrrigation._build_preview` |  |
| 298 | `DSG_OT_StartIrrigation.invoke` |  |
| 330 | class `DSG_OT_UpdateIrrigationPreview` | `dsg.update_irrigation_preview` · Update Walls from Path |
| 335 | `DSG_OT_UpdateIrrigationPreview.execute` |  |
| 379 | class `DSG_OT_ShowExactIrrigationLumenDiagnostic` | `dsg.show_exact_irrigation_lumen_diagnostic` · Show Checked Water Lumen |
| 384 | `DSG_OT_ShowExactIrrigationLumenDiagnostic.execute` |  |
| 436 | class `DSG_OT_ConfirmIrrigationPreview` | `dsg.confirm_irrigation_preview` · Confirm |
| 441 | `DSG_OT_ConfirmIrrigationPreview.execute` |  |
| 529 | class `DSG_OT_UpdateConfirmIrrigation` | `dsg.update_confirm_irrigation` · Confirm |
| 534 | `DSG_OT_UpdateConfirmIrrigation.execute` |  |
| 554 | `_closest_point_on_segment` |  |
| 566 | `_closest_point_tangent_on_irrigation_entry` |  |
| 593 | `_closest_point_on_irrigation_entry` |  |
| 610 | `_find_irrigation_entry_by_index` |  |
| 624 | `_implant_has_irrigation_entry` |  |
| 635 | `_remove_irrigation_link_markers` |  |
| 644 | `_create_irrigation_link_marker` |  |
| 661 | `_raycast_confirmed_irrigation_wall` | Returns the confirmed irrigation wall directly clicked by the user. |
| 693 | `_build_irrigation_link_controls_from_points` | Creates an adaptive Y from scratch around the selected source region. |
| 789 | `build_irrigation_link_y_parts` | Builds the explicit curved three-leg lumen used for diagnostics/fallback. |
| 833 | class `DSG_OT_LinkIrrigation` | `dsg.link_irrigation` · Link |
| 843 | `DSG_OT_LinkIrrigation._finish` |  |
| 851 | `DSG_OT_LinkIrrigation._cancel` |  |
| 857 | `DSG_OT_LinkIrrigation._commit_link` |  |
| 990 | `DSG_OT_LinkIrrigation.modal` |  |
| 1099 | `DSG_OT_LinkIrrigation.invoke` |  |
| 1129 | class `DSG_OT_RemoveLastIrrigation` | `dsg.remove_last_irrigation` · Delete |
| 1134 | `DSG_OT_RemoveLastIrrigation.execute` |  |
| 1184 | class `DSG_OT_CancelIrrigationPreview` | `dsg.cancel_irrigation_preview` · Discard Preview |
| 1189 | `DSG_OT_CancelIrrigationPreview.execute` |  |
| 1201 | class `DSG_OT_SkipIrrigation` | `dsg.skip_irrigation` · Skip Irrigation |
| 1206 | `DSG_OT_SkipIrrigation.execute` |  |
| 1252 | `repair_irrigation_open_component` | Cierra únicamente bucles abiertos simples antes del Boolean de irrigación. |
| 1346 | `_irrigation_flow_simulation_objects` |  |
| 1354 | `clear_irrigation_flow_simulation` |  |
| 1382 | `_ensure_irrigation_flow_material` |  |
| 1435 | `_polyline_length` |  |
| 1441 | `_remove_near_duplicate_samples` |  |
| 1457 | `_flow_samples_from_samples` |  |
| 1464 | `_build_c_outlet_samples_for_simulation` |  |
| 1497 | `_append_terminal_c_paths` |  |
| 1523 | `build_irrigation_flow_simulation_routes` | Builds inlet-to-outlet sample paths for the final water-volume preview. |
| 1614 | `_route_length_from_samples` |  |
| 1619 | `_normalize_dsg_object_name` | Normalizes Blender duplicate suffixes and harmless name variations. |
| 1627 | `_animation_windows_for_drills` | Returns rich drill windows instead of relying only on an exact name key. |
| 1662 | `_resolve_drill_window_for_route` | Matches one irrigation route to its drill with several safe fallbacks. |
| 1700 | `_set_linear_animation_on_id` |  |
| 1712 | `_create_irrigation_flow_curve_object` | Creates the animated internal water volume along one irrigation route. |
| 1774 | `_animate_flow_curve_object` |  |
| 1804 | `_ensure_viewport_particle_material` | Blue viewport-only material, slightly darker than the internal water. |
| 1822 | `_ensure_solid_material_coloring` | Make the active Solid view use material colors so blue particles are visible. |
| 1839 | `_create_shared_viewport_particle_mesh` |  |
| 1849 | `_particle_outlet_basis` |  |
| 1868 | `_animate_viewport_particle` | Keyframes one ballistic flight; no particle system or emitter is used. |
| 1915 | `_create_viewport_water_particles` | Creates blue animated viewport particles directly, with no emitter objects. |
| 2049 | `_set_rna_if_present` |  |
| 2060 | `_make_world_box_mesh` | Creates an axis-aligned closed box using actual world coordinates. |
| 2083 | `_ensure_fluid_effector` |  |
| 2105 | `_resolve_irrigation_entry_implant` |  |
| 2118 | `_cascade_vectors_for_event` |  |
| 2151 | class `DSG_OT_SimulateIrrigationFlow` | `dsg.simulate_irrigation_flow` · Update Solid Water Flow |
| 2159 | `DSG_OT_SimulateIrrigationFlow.execute` |  |
| 2292 | class `DSG_OT_ClearIrrigationFlowSimulation` | `dsg.clear_irrigation_flow_simulation` · Clear Irrigation Simulation |
| 2298 | `DSG_OT_ClearIrrigationFlowSimulation.execute` |  |
| 2308 | class `DSG_OT_ConfirmIrrigation` | `dsg.confirm_irrigation` · Apply Irrigation and Continue |
| 2313 | `DSG_OT_ConfirmIrrigation.execute` |  |

## [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py)

2713 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | `get_pending_reinforcement_preview` |  |
| 11 | `get_confirmed_reinforcement_curves` |  |
| 26 | `_orient_surface_normal_to_view` |  |
| 37 | `_build_guide_bvh` |  |
| 51 | `_nearest_guide_surface` |  |
| 73 | `_catmull_rom_knot` |  |
| 78 | `_catmull_rom_centripetal_segment` | Muestrea el tramo P1→P2 con parametrización centrípeta. |
| 91 | `_catmull_rom_centripetal_segment.blend` |  |
| 111 | `_sample_centripetal_catmull_rom` |  |
| 135 | `_reinforcement_outward_direction` |  |
| 151 | `_raycast_evaluated_reinforcement_target` | Raycast individual sobre MESH o CURVE evaluada. |
| 220 | `raycast_reinforcement_support` | Devuelve el apoyo visible más cercano entre guía y refuerzos confirmados. |
| 243 | `remove_reinforcement_markers` |  |
| 254 | `refresh_reinforcement_markers` |  |
| 275 | `_clean_reinforcement_chain` |  |
| 293 | `_build_world_surface_bvh` | Construye un BVH en coordenadas World para MESH o CURVE evaluada. |
| 326 | `_nearest_support_surface_world` |  |
| 346 | `_bvh_world_ray_distance` |  |
| 364 | `_bvh_world_ray_hit_count` | Count BVH ray hits while stepping past each intersection. |
| 393 | `_bvh_point_inside_solid` | Best-effort inside test for closed model cutters. |
| 443 | `_estimate_support_axis_half_span` | Estimación conservadora de cuánto cabe una huella centrada en el contacto. |
| 479 | `_cubic_bezier_point` |  |
| 488 | `_ring_centroid` |  |
| 497 | `_smooth_circular_ring` |  |
| 516 | `_equalize_ring_radii` |  |
| 555 | `_regularize_and_fullen_ring` |  |
| 586 | `_polyline_cumulative_lengths` |  |
| 596 | `_polyline_point_at_distance` |  |
| 613 | `_trim_polyline_by_distances` | Recorta una polilínea por longitud de arco sin cambiar su trayectoria. |
| 640 | `_polyline_vertex_tangents` |  |
| 662 | `_signed_angle_around_axis` |  |
| 671 | `_preferred_reinforcement_tube_u` | Eje transversal estable: evita el giro de Frenet cerca de tramos rectos. |
| 687 | `_create_open_rotation_minimizing_tube` | Tubo abierto barrido por transporte paralelo con corrección de giro final. |
| 803 | `_reinforcement_extended_neck_length` |  |
| 814 | `_reinforcement_consistent_endpoint_frames` | Construye la misma parametrización geométrica en ambos extremos. |
| 922 | `_build_reinforcement_coons_blend_object` | Collar Coons-Hermite extendido desde el apoyo hasta el tubo recortado. |
| 1234 | `_sample_reinforcement_two_point_segment` | Genera UN tramo entre dos puntos consecutivos. |
| 1276 | `_build_reinforcement_segmented_chain` | Crea la cadena completa como suma de tramos consecutivos independientes. |
| 1310 | `build_reinforcement_chain_preview` | Cadena segmentada con cuerpo recortado y collars Coons-Hermite largos. |
| 1546 | `build_reinforcement_bezier_preview` | Compatibilidad con llamadas antiguas: crea una cadena simple de dos puntos. |
| 1554 | `reinforcement_curve_to_mesh` | Devuelve una copia MESH tanto si el refuerzo fuente es CURVE como MESH. |
| 1616 | class `DSG_OT_CreateAnimatedDrills` | `dsg.create_animated_drills` · Create Animated Drills |
| 1621 | `DSG_OT_CreateAnimatedDrills.execute` |  |
| 1672 | class `DSG_OT_PlayAnimatedDrills` | `dsg.play_animated_drills` · Play Drill Insertion |
| 1676 | `DSG_OT_PlayAnimatedDrills.execute` |  |
| 1698 | class `DSG_OT_StopAnimatedDrills` | `dsg.stop_animated_drills` · Stop Drill Animation |
| 1702 | `DSG_OT_StopAnimatedDrills.execute` |  |
| 1721 | class `DSG_OT_ToggleAnimatedDrillsVisibility` | `dsg.toggle_animated_drills_visibility` · Show or Hide Animated Drills |
| 1725 | `DSG_OT_ToggleAnimatedDrillsVisibility.execute` |  |
| 1752 | class `DSG_OT_ShowAnimatedDrillStart` | `dsg.show_animated_drill_start` · Show Start Position |
| 1756 | `DSG_OT_ShowAnimatedDrillStart.execute` |  |
| 1765 | class `DSG_OT_ShowAnimatedDrillStop` | `dsg.show_animated_drill_stop` · Show Maximum Insertion |
| 1769 | `DSG_OT_ShowAnimatedDrillStop.execute` |  |
| 1785 | `_microscrew_records_for_animation` | Use live confirmed geometry when available; JSON is the post-fusion fallback. |
| 1800 | `configure_sequential_insertion_frames` | Orders extraction first (immediate route), then guide seating, screws, |
| 1933 | `get_sequential_insertion_bounds` |  |
| 1957 | class `DSG_OT_CreateSequentialInsertionAnimation` | `dsg.create_sequential_insertion_animation` · Create Screw, Drill and Implant Sequence |
| 1962 | `DSG_OT_CreateSequentialInsertionAnimation.execute` |  |
| 2123 | class `DSG_OT_UpdateFinalAnimation` | `dsg.update_final_animation` · Update Final Animation |
| 2131 | `DSG_OT_UpdateFinalAnimation.execute` |  |
| 2184 | class `DSG_OT_PlaySequentialInsertionAnimation` | `dsg.play_sequential_insertion_animation` · Play Screw, Drill and Implant Sequence |
| 2188 | `DSG_OT_PlaySequentialInsertionAnimation.execute` |  |
| 2225 | class `DSG_OT_StopSequentialInsertionAnimation` | `dsg.stop_sequential_insertion_animation` · Stop Insertion Sequence |
| 2229 | `DSG_OT_StopSequentialInsertionAnimation.execute` |  |
| 2265 | class `DSG_OT_ToggleSequentialInsertionVisibility` | `dsg.toggle_sequential_insertion_visibility` · Show or Hide Screws, Drills and Implants |
| 2269 | `DSG_OT_ToggleSequentialInsertionVisibility.execute` |  |
| 2295 | class `DSG_OT_StartReinforcement` | `dsg.start_reinforcement` · Draw Reinforcement Chain |
| 2300 | `DSG_OT_StartReinforcement._remove_markers` |  |
| 2303 | `DSG_OT_StartReinforcement._remove_working_preview` |  |
| 2309 | `DSG_OT_StartReinforcement._refresh_markers` |  |
| 2313 | `DSG_OT_StartReinforcement._rebuild_preview` |  |
| 2331 | `DSG_OT_StartReinforcement._finish_modal` |  |
| 2336 | `DSG_OT_StartReinforcement._cancel_modal` |  |
| 2340 | `DSG_OT_StartReinforcement.modal` |  |
| 2461 | `DSG_OT_StartReinforcement.invoke` |  |
| 2492 | class `DSG_OT_ConfirmReinforcementPreview` | `dsg.confirm_reinforcement_preview` · Confirm Reinforcement Connector |
| 2497 | `DSG_OT_ConfirmReinforcementPreview.execute` |  |
| 2529 | class `DSG_OT_CancelReinforcementPreview` | `dsg.cancel_reinforcement_preview` · Discard Pending Connector |
| 2534 | `DSG_OT_CancelReinforcementPreview.execute` |  |
| 2547 | class `DSG_OT_RemoveLastReinforcement` | `dsg.remove_last_reinforcement` · Delete Last Connector |
| 2552 | `DSG_OT_RemoveLastReinforcement.execute` |  |
| 2566 | class `DSG_OT_SkipReinforcement` | `dsg.skip_reinforcement` · Skip Reinforcement Connectors |
| 2571 | `DSG_OT_SkipReinforcement.execute` |  |
| 2600 | class `DSG_OT_ApplyReinforcements` | `dsg.apply_reinforcements` · Add Connectors and Continue |
| 2605 | `DSG_OT_ApplyReinforcements.execute` |  |

## [_guide_parts/07b_presentation_animation.py](../_guide_parts/07b_presentation_animation.py)

311 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 33 | `_clear_color_keys` |  |
| 40 | `_key_color` |  |
| 45 | `_constant_color_keys` |  |
| 53 | `_with_alpha` |  |
| 57 | `_tag_presentation` |  |
| 65 | `clear_presentation_animation` | Remove rings and colour keys; restore each object's previous colour. |
| 85 | `_is_cbct_object` |  |
| 92 | `_torus_mesh` |  |
| 117 | `_build_site_ring` |  |
| 145 | `_flash` |  |
| 152 | `apply_presentation_animation` | Colour keys and work rings driven by the sequence timeline. |
| 243 | `_iter_view3d_spaces` |  |
| 256 | `enter_presentation_view` |  |
| 287 | `exit_presentation_view` |  |

## [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py)

3783 líneas · imports Blender: ninguno directo · namespace de `guide_module`

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 1 | class `DSG_OT_PlaceEngraveAnchor` | `dsg.place_engrave_anchor` · Place Name on Surface |
| 6 | `DSG_OT_PlaceEngraveAnchor.invoke` |  |
| 22 | `DSG_OT_PlaceEngraveAnchor.modal` |  |
| 51 | class `DSG_OT_UpdateEngravePreview` | `dsg.update_engrave_preview` · Update Preview |
| 56 | `DSG_OT_UpdateEngravePreview.execute` |  |
| 74 | class `DSG_OT_ClearEngravePreview` | `dsg.clear_engrave_preview` · Clear Preview |
| 79 | `DSG_OT_ClearEngravePreview.execute` |  |
| 91 | class `DSG_OT_ApplyPatientEngrave` | `dsg.apply_patient_engrave` · Engrave Name on Guide |
| 96 | `DSG_OT_ApplyPatientEngrave.execute` |  |
| 155 | class `DSG_OT_SkipPatientName` | `dsg.skip_patient_name` · Continue Without Name |
| 160 | `DSG_OT_SkipPatientName.execute` |  |
| 176 | class `DSG_OT_CleanGuideIslands` | `dsg.clean_guide_islands` · Remove Separate Fragments |
| 181 | `DSG_OT_CleanGuideIslands.execute` |  |
| 201 | class `DSG_OT_ExportGuideSTL` | `dsg.export_guide_stl` · Export Guide STL |
| 229 | `DSG_OT_ExportGuideSTL.invoke` |  |
| 240 | `DSG_OT_ExportGuideSTL.execute` |  |
| 447 | class `DSG_OT_ToggleBlockoutVisibility` | `dsg.toggle_blockout_visibility` · Show/Hide Model |
| 452 | `DSG_OT_ToggleBlockoutVisibility.execute` |  |
| 468 | class `DSG_OT_ToggleGuideVisibility` | `dsg.toggle_guide_visibility` · Show/Hide Guide |
| 473 | `DSG_OT_ToggleGuideVisibility.execute` |  |
| 487 | `_final_cbct_stl_objects` | Return only the 3D STL meshes generated from the CBCT segmentation. |
| 511 | `_prepare_final_overlay_view` | Prepare the final review without hiding the surgical guide. |
| 531 | `_toggle_final_reference_layer` | Toggle one final reference layer without changing other visible layers. |
| 549 | class `DSG_OT_FinalViewModel` | `dsg.final_view_model` · Toggle Model Layer |
| 554 | `DSG_OT_FinalViewModel.execute` |  |
| 571 | class `DSG_OT_FinalViewCBCTSTL` | `dsg.final_view_cbct_stl` · Toggle CBCT STL Layer |
| 576 | `DSG_OT_FinalViewCBCTSTL.execute` |  |
| 606 | `apply_object_scale_for_final` | Aplica únicamente la escala para que el voxel esté expresado en milímetros reales. |
| 627 | `apply_final_voxel_remesh` | Convierte una malla o conjunto de shells en una única superficie voxelizada. |
| 662 | `decimate_final_mesh` | Reduce polígonos con Collapse únicamente cuando supera el objetivo. |
| 695 | `build_final_solid_cutter` | Prepara modelo + blockout como cutter sólido y ligero. |
| 817 | `_object_local_bounds` |  |
| 839 | `_object_world_bounds_center` |  |
| 852 | `_trim_unprojected_proxy_vertices` | Elimina celdas del grid que Shrinkwrap no logró proyectar. |
| 885 | `build_final_shrinkwrap_proxy_cutter` | Construye un cutter sólido de tipo height-field para STL intraoral abierto. |
| 1112 | `build_final_cutter_auto` | Selecciona automáticamente cutter voxel normal o proxy Shrinkwrap. |
| 1144 | `get_supported_boolean_solvers` |  |
| 1152 | `apply_final_boolean_prepared` | Applies the final DIFFERENCE transactionally and validates each solver. |
| 1246 | `repair_small_final_nonmanifold` | Cierra únicamente aberturas finales pequeñas sin remallar toda la guía. |
| 1325 | `validate_final_result_light` | Validación corta: nunca ejecuta la auditoría BMesh de millones de edges. |
| 1342 | class `DCT_OT_VoxelRemesh` | `dct.voxel_remesh` · Apply Voxel Remesh |
| 1348 | `DCT_OT_VoxelRemesh.execute` |  |
| 1364 | class `DCT_OT_SelectBeingCut` | `dct.select_being_cut` · Select Object Being Cut |
| 1369 | `DCT_OT_SelectBeingCut.execute` |  |
| 1379 | class `DCT_OT_SelectMakingCut` | `dct.select_making_cut` · Select Object Making Cut |
| 1384 | `DCT_OT_SelectMakingCut.execute` |  |
| 1403 | class `DCT_OT_ApplyCut` | `dct.apply_cut` · Apply Final Boolean |
| 1408 | `DCT_OT_ApplyCut.execute` |  |
| 1453 | `DCT_OT_ApplyCut.execute.cancel` |  |
| 1670 | class `DSG_OT_ContinueToNameExport` | `dsg.continue_to_name_export` · Continue to Name and Export |
| 1675 | `DSG_OT_ContinueToNameExport.execute` |  |
| 1696 | class `DCT_OT_ClearCutSelection` | `dct.clear_cut_selection` · Clear Selection |
| 1701 | `DCT_OT_ClearCutSelection.execute` |  |
| 1713 | `draw_preflight_semaphore` |  |
| 1746 | `get_sleeve_preflight_summary` | Resumen ligero para UI; nunca recorre una malla dentro de ``Panel.draw``. |
| 1788 | `get_step10_diagnostic` |  |
| 1803 | `_draw_reset_flow_panel` | Navigation is centralized in DSG > Control del flujo (v9.2.5). |
| 1808 | `_draw_collapsible_sequence_panel` | Optional final animation controls, closed by default. |
| 1826 | `_primary_action` | Direct/mandatory route using the shared DSG hierarchy. |
| 1831 | `_secondary_action` | Optional efficacy route using the shared DSG hierarchy. |
| 1836 | `_secondary_box` |  |
| 1842 | `_tertiary_header` |  |
| 1853 | `_compact_tools` | Tertiary/accessory tools, compact and visually discreet. |
| 1858 | `_step_progress_text` | Ten visual dots for DSG only: filled through the current stage. |
| 1867 | `_draw_step_model_axis` | Clinical first step: orient, choose retention, calculate and confirm. |
| 2070 | `_draw_step_blockout` |  |
| 2074 | `_draw_step_contour` |  |
| 2176 | `_draw_dicom_review_box_for_guide_step` | Contextual DICOM review, visually secondary unless already active. |
| 2218 | `_draw_implant_passive_blockout_box` | Compact recovery card for an unconfirmed retentive model. |
| 2255 | `_draw_implant_dicom_review` |  |
| 2296 | `_immediate_target_tooth` | Return the TotalSegmentator tooth object selected as the extraction target. |
| 2317 | `_immediate_extraction_ready` |  |
| 2343 | `restore_immediate_extraction` | Restore a virtually extracted tooth and clear route-specific state. |
| 2375 | class `DSG_OT_PrepareImmediateExtraction` | `dsg.prepare_immediate_extraction` · Prepare Immediate Extraction |
| 2381 | `DSG_OT_PrepareImmediateExtraction.execute` |  |
| 2416 | class `DSG_OT_RestoreImmediateTooth` | `dsg.restore_immediate_tooth` · Restore Immediate Tooth |
| 2422 | `DSG_OT_RestoreImmediateTooth.execute` |  |
| 2429 | `_draw_immediate_implant_gate` |  |
| 2503 | `_draw_step_implant` |  |
| 2598 | `_raw` | Underlying Blender layout (section titles bypass the minimal-UI proxy). |
| 2603 | `_section` |  |
| 2609 | `_draw_implant_mpr_list` | 2 · Radiographic review: target implant, open/exit, and the MPR planes |
| 2654 | `_draw_sequential_insertion_animation` |  |
| 2689 | `_draw_frame_boolean_prediction` | Predicted state of the frame after the final Boolean (geodesic sections). |
| 2708 | `_draw_step_frame` |  |
| 2764 | `_draw_step_sleeve` |  |
| 2814 | `_draw_irrigation_implant_gates` |  |
| 2835 | `_draw_irrigation_mode_selector` |  |
| 2856 | `_draw_step_irrigation` |  |
| 3017 | `_draw_geodesic_research_tools` | Show all diagnostic-only FEM tools also after routes are confirmed. |
| 3045 | `_draw_step_reinforcement` |  |
| 3117 | `_draw_step_drill` |  |
| 3126 | `_draw_step_final_cut` |  |
| 3141 | `_draw_step_name_export` |  |
| 3223 | class `_DSGMinimalUILayout` | Proxy that removes passive panel copy while preserving interactive UI. |
| 3232 | `_DSGMinimalUILayout.__init__` |  |
| 3237 | `_DSGMinimalUILayout.__getattr__` |  |
| 3240 | `_DSGMinimalUILayout.__setattr__` |  |
| 3248 | `_DSGMinimalUILayout._wrap` |  |
| 3251 | `_DSGMinimalUILayout.row` |  |
| 3254 | `_DSGMinimalUILayout.column` |  |
| 3257 | `_DSGMinimalUILayout.box` |  |
| 3260 | `_DSGMinimalUILayout.split` |  |
| 3263 | `_DSGMinimalUILayout.grid_flow` |  |
| 3266 | `_DSGMinimalUILayout.label` |  |
| 3276 | class `DSG_PT_Main` | `DSG_PT_main` · DSG |
| 3285 | `DSG_PT_Main.poll` |  |
| 3291 | `DSG_PT_Main.draw` |  |
| 3486 | `_dsg_migrate_irrigation_outlet_to_1mm` | Actualiza una sola vez el antiguo valor predeterminado de 0,80 a 1,00 mm. |
| 3558 | `_dsg_remove_load_handler` |  |
| 3566 | `pre_register_quiesce` | Remove callbacks from older DSG builds without reading bpy.data. |
| 3578 | `_dsg_remove_scene_pointer` |  |
| 3590 | `_dsg_unregister_class_object` |  |
| 3600 | `_dsg_unregister_stale_classes` | Removes classes left registered by an older addon file. |
| 3622 | `_dsg_rollback_registration` |  |
| 3628 | `_dsg_is_class_registered` | Checks class registration without relying on bpy.types.<class name>. |
| 3642 | `register` |  |
| 3700 | `deferred_post_register` | Recover existing DSG state after Blender restores normal data access. |
| 3745 | `unregister` |  |

## [agent_core.py](../agent_core.py)

145 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | class `AgentToolSpec` |  |
| 27 | `AgentToolSpec.agent_callable` |  |
| 100 | `canonical_hash` |  |
| 106 | `capability_manifest` |  |
| 120 | `find_journal_entry` |  |
| 127 | `begin_journal` |  |

## [agent_facade.py](../agent_facade.py)

283 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 46 | `_utc_now` |  |
| 50 | `_require_main_thread` |  |
| 58 | `_scene` |  |
| 65 | `_load_journal` |  |
| 76 | `_save_journal` |  |
| 81 | `_serializable_result` |  |
| 90 | `_bridge_module` |  |
| 96 | `get_capabilities` |  |
| 118 | `get_operation_history` |  |
| 129 | `get_operation_status` |  |
| 146 | `_prepare_args` |  |
| 163 | `_dispatch` |  |
| 174 | `run_agent_tool` | Run one closed-capability agent tool on Blender's main thread. |
| 278 | `register` |  |
| 282 | `unregister` |  |

## [agent_scene_graph.py](../agent_scene_graph.py)

224 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 27 | class `_GraphCache` |  |
| 37 | `_scene_key` |  |
| 44 | `_cache` |  |
| 53 | `current_revision` |  |
| 57 | `mark_dirty` |  |
| 63 | `_is_relevant` |  |
| 73 | `_safe_prop` |  |
| 87 | `_vec3` |  |
| 94 | `_object_uid` |  |
| 104 | `_node` |  |
| 125 | `_relations` |  |
| 148 | `_build` |  |
| 167 | `get_scene_graph` |  |
| 177 | `get_scene_graph_summary` |  |
| 189 | `_depsgraph_handler` |  |
| 207 | `register` |  |
| 216 | `unregister` |  |

## [alignment_module.py](../alignment_module.py)

9 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [anatomy_refine.py](../anatomy_refine.py)

610 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 25 | class `RefineProfile` |  |
| 99 | `_mesh_volume` |  |
| 109 | `_vertex_normals` |  |
| 125 | `_laplacian_delta` | Uniform umbrella Laplacian without Python adjacency sets. |
| 144 | `_taubin` |  |
| 154 | `_cap_displacement` |  |
| 166 | `_try_mmg` | Best-effort MMG surface remesh for teeth only. |
| 207 | `_build_sdf` |  |
| 224 | `_sample_grid` |  |
| 230 | `_sample_local_mask` | Trilinear mask sampling in bounded chunks without materialising float volumes. |
| 243 | `_project_to_mask_surface` | Fast local cage projection onto the learned 0.5 mask isosurface. |
| 304 | `_project_to_sdf` |  |
| 336 | `_clamp_sdf_band` |  |
| 361 | `_cbct_edge_snap` | Move vertices toward a strong local radiographic edge within the mask band. |
| 415 | `_volume_guard` |  |
| 443 | `refine_segmented_surface` | Responsive CBCT-constrained refinement without volumetric EDT bottlenecks. |

## [blender/__init__.py](../blender/__init__.py)

1 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [blender/arch_base.py](../blender/arch_base.py)

197 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 23 | `arc_gaussian` | Gaussian low-pass of a closed 2-D polyline over its arc length. |
| 38 | `signed_area` |  |
| 43 | `inward_normals` | Unit inward normals, averaged over ``sigma`` of arc length. |
| 61 | `_smooth_field` |  |
| 77 | `_orient` |  |
| 81 | `is_simple` | True when no two non-adjacent edges of the closed polygon cross. |
| 110 | `plan` | Ring positions from the collar to the lid outline, or (None, reason). |
| 163 | `build` | Create collar, wall, rounded edge and U lid in ``bm``; None if not valid. |

## [blender/blockout_field.py](../blender/blockout_field.py)

63 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `blockout_shift` | Axial fill per vertex for a retention value, without pits or holes. |
| 44 | `blockout_shift.neighbour_mean` |  |

## [blender/cylinder_contact.py](../blender/cylinder_contact.py)

61 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `clip_z` |  |
| 17 | `intersects` |  |

## [blender/deferred.py](../blender/deferred.py)

52 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 13 | `run_later` |  |
| 18 | `run_later._tick` |  |
| 29 | `assign` | Set an RNA attribute only when it changes (avoids redraw loops). |
| 37 | `assign_key` |  |
| 44 | `set_hidden` |  |

## [blender/evaluated_visible.py](../blender/evaluated_visible.py)

31 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `visible` |  |

## [blender/extraction_extension.py](../blender/extraction_extension.py)

145 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 10 | `update` |  |
| 25 | `property_definition` |  |
| 30 | `preview` |  |
| 99 | class `DSG_OT_ExtensionPreview` | `dsg.extraction_extension_preview` · VER EXTENSIÓN OCLUSAL |
| 103 | `DSG_OT_ExtensionPreview.execute` |  |
| 110 | class `DSG_OT_ToggleExtractionSmoothing` | `dsg.toggle_extraction_tooth_smoothing` · Suavizado del diente a extraer |
| 116 | `DSG_OT_ToggleExtractionSmoothing.execute` |  |
| 130 | `draw` |  |

## [blender/frame_embed.py](../blender/frame_embed.py)

232 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 31 | `_circular` |  |
| 36 | `_gaussian` |  |
| 41 | `_envelope` | Smooth requirement that never falls below (or above) the original. |
| 48 | `_geodesic_band` | Surface vertices within ~1.3 radius of the route, measured on the shell. |
| 75 | `_frames` |  |
| 93 | `predict` | Retained thickness, embed depth and support for every station. |
| 125 | `_corridor` | Allowed shift along the normal for every station (outward positive). |
| 150 | `_minimum_bending` | Least-bending profile inside the corridor (projected bi-Laplacian). |
| 166 | `solve` | Smoothest centreline inside the clinical corridor (thicken if needed). |
| 224 | `optimise` |  |

## [blender/implant_optimizer.py](../blender/implant_optimizer.py)

669 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 15 | `target` |  |
| 19 | `settings` |  |
| 25 | `geometry_objects` |  |
| 36 | `fingerprint` | Everything a proposal depends on.  The .blend path is not part of it, so |
| 51 | `catalogue_signature` |  |
| 64 | `readiness` |  |
| 84 | `_catalogue` |  |
| 104 | `current_size` | Identity of the implant being compared: catalogue id and nominal size. |
| 111 | `snapshot` |  |
| 118 | `snapshot.export` |  |
| 131 | `snapshot.add` |  |
| 167 | `remove_preview` |  |
| 176 | `stop` |  |
| 185 | `clean_jobs` |  |
| 197 | `discard` |  |
| 201 | `on_load` |  |
| 204 | `start` |  |
| 233 | `_preview` |  |
| 283 | `_matches` |  |
| 286 | `_commit_nominal` | Apply a nominal catalogue size with DSG's own implant mesh. |
| 336 | `_commit` |  |
| 386 | `poll` |  |
| 432 | class `DSG_OT_OptimizePosition` | `dsg.optimize_implant_position` · BUSCAR POSICIÓN |
| 434 | `DSG_OT_OptimizePosition.execute` |  |
| 438 | class `DSG_OT_OptimizeSize` | `dsg.optimize_implant_size` · COMPARAR TAMAÑOS |
| 440 | `DSG_OT_OptimizeSize.execute` |  |
| 444 | class `DSG_OT_ApplyOptimization` | `dsg.apply_implant_optimization` · ACEPTAR CAMBIOS |
| 449 | `DSG_OT_ApplyOptimization.execute` |  |
| 453 | class `DSG_OT_DiscardOptimization` | `dsg.discard_implant_optimization` · DESCARTAR CAMBIOS / CANCELAR |
| 455 | `DSG_OT_DiscardOptimization.execute` |  |
| 458 | `library_changed` |  |
| 464 | `register` |  |
| 502 | `unregister` |  |
| 513 | `draw` |  |
| 621 | `draw_surround` |  |
| 631 | `restore_visibility` |  |
| 642 | `recover_saved_previews` |  |
| 653 | `restore_followers` |  |
| 660 | `watch_preview` |  |

## [blender/implant_optimizer_geometry.py](../blender/implant_optimizer_geometry.py)

308 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 9 | class `Solid` |  |
| 10 | `Solid.__init__` | ``topology`` = (witness vertex indices) from a verified identical mesh. |
| 34 | `Solid.tree` |  |
| 37 | `Solid._ray_contains` |  |
| 48 | `Solid.contains` |  |
| 59 | `Solid.signed_distances` |  |
| 67 | `transformed` |  |
| 71 | `clearance` |  |
| 81 | `clearance.distance` |  |
| 87 | `surface_samples` |  |
| 96 | `measure_surrounding_bone` | Sample radial gaps and first native-bone wall, in mm; never fills a socket. |
| 135 | `invasion_depth` | Deepest implant point inside a tolerated zone (mm); None if it does not cross it. |
| 146 | `invasion_depth.deepest` |  |
| 159 | `bone_reserve` | Conservative lateral/apical wall reserve below a free cervical band. |
| 193 | class `Evaluator` | Same hard constraints for both searches: exclusions, wall reserve, coverage. |
| 195 | `Evaluator.__init__` |  |
| 200 | `Evaluator._prepare` |  |
| 222 | `Evaluator.__call__` |  |
| 230 | `Evaluator.check_structures` |  |
| 254 | `Evaluator._strict` |  |
| 288 | `Evaluator.socket_split` | (mask of points in native bone region, apical engagement beyond the socket in mm). |
| 299 | `Evaluator.measure_bone` |  |

## [blender/implant_plane.py](../blender/implant_plane.py)

472 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 44 | `selected_implant` |  |
| 58 | `plane_for` |  |
| 64 | `planes` |  |
| 68 | `visible` |  |
| 72 | `_remove` |  |
| 79 | `cleanup` | Remove planes whose implant no longer exists, and the old flat ones. |
| 92 | `_mesh` | Image quad (material 0) inside a coloured frame (material 1), XY plane. |
| 112 | `_frame_material` |  |
| 131 | `_arch_centre` |  |
| 139 | `_angle_about_axis` | Rotation about the implant's local Z that makes the plane mesio-distal |
| 157 | `_default_color` |  |
| 165 | `create` |  |
| 204 | `_angle_changed` | Rotate only this section around the implant axis and queue its reslice. |
| 218 | `register_angle` |  |
| 229 | `set_color` |  |
| 236 | `_ensure_voxels` |  |
| 250 | `refresh` | Reslice the CBCT on the plane (same sampling as the DICOM MPR planes). |
| 284 | `_pose_key` |  |
| 288 | `_refresh_pending` |  |
| 302 | `_follow` | Reslice when an implant moves (debounced). |
| 317 | `set_visible` | Show/hide the planes.  While a plane (or the DICOM review) is shown the |
| 340 | class `DSG_OT_CreateInclinationPlane` | `dsg.create_implant_inclination_plane` · Plano radiográfico del implante |
| 347 | `DSG_OT_CreateInclinationPlane.execute` |  |
| 360 | class `DSG_OT_RotateInclinationPlane` | `dsg.rotate_implant_inclination_plane` · Orientación del plano |
| 366 | `DSG_OT_RotateInclinationPlane.execute` |  |
| 377 | class `DSG_OT_ColorInclinationPlane` | `dsg.color_implant_inclination_plane` · Color del marco |
| 383 | `DSG_OT_ColorInclinationPlane.execute` |  |
| 393 | class `DSG_OT_ToggleInclinationPlanes` | `dsg.toggle_implant_inclination_planes` · Mostrar/ocultar planos del implante |
| 398 | `DSG_OT_ToggleInclinationPlanes.execute` |  |
| 407 | `draw` |  |
| 432 | `register` |  |
| 438 | `unregister` |  |
| 447 | `draw_rows` | Implant plane entry for the MPR list (eye + create + options). |

## [blender/implant_resize.py](../blender/implant_resize.py)

93 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 13 | `target_implant` |  |
| 29 | `resize` | Rebuild the implant mesh at the new size; returns True if it changed. |
| 63 | `on_diameter_changed` |  |
| 67 | `on_length_changed` |  |
| 71 | `on_size_changed` | FloatProperty update callback; each field changes only its own size. |

## [blender/ios_guided_selection.py](../blender/ios_guided_selection.py)

335 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 11 | `activate_circle` |  |
| 22 | `set_circle_mode` | ADD keeps every brush stroke (several passes); SUB erases mistakes. |
| 29 | `circle_mode` |  |
| 33 | `_components` |  |
| 50 | `_ring` |  |
| 54 | `_fill_holes` | Add unselected pockets fully enclosed by the region (bounded flood). |
| 81 | `_bowties` | Rim vertices touched by the region more than once (rim would cross). |
| 93 | `clean_region` | Turn the brushed selection into one clean disc of faces. |
| 121 | `_saved_faces` |  |
| 131 | `store_region` | Mark the region in a face layer; returns the region re-fetched. |
| 150 | `selected_copy` |  |
| 160 | `remove_saved` |  |
| 171 | `show_region` |  |
| 179 | `smooth_rim` | Tangential rim smoothing that never flips a face. |
| 198 | `smooth_rim.acceptable` |  |
| 227 | class `DSG_OT_IOSSaveToothSelection` | `dsg.ios_save_tooth_selection` · GUARDAR SELECCIÓN (P) |
| 234 | `DSG_OT_IOSSaveToothSelection.poll` |  |
| 238 | `DSG_OT_IOSSaveToothSelection.execute` |  |
| 249 | `save_current_selection` | Clean the current brush selection, check its rim and store it. |
| 271 | class `DSG_OT_IOSSelectionMode` | `dsg.ios_selection_mode` · Modo de selección |
| 277 | `DSG_OT_IOSSelectionMode.execute` |  |
| 286 | class `DSG_OT_IOSClearSelection` | `dsg.ios_clear_selection` · Empezar selección de nuevo |
| 292 | `DSG_OT_IOSClearSelection.poll` |  |
| 295 | `DSG_OT_IOSClearSelection.execute` |  |
| 302 | class `DSG_OT_IOSCircleSelection` | `dsg.ios_circle_selection` · Seleccionar con círculo (C) |
| 307 | `DSG_OT_IOSCircleSelection.poll` |  |
| 311 | `DSG_OT_IOSCircleSelection.execute` |  |
| 319 | `register` |  |
| 329 | `unregister` |  |

## [blender/ios_skip_removal.py](../blender/ios_skip_removal.py)

47 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | class `DSG_OT_IOSSkipToothRemoval` | `dsg.ios_skip_tooth_removal` · SIGUIENTE |
| 14 | `DSG_OT_IOSSkipToothRemoval.poll` |  |
| 18 | `DSG_OT_IOSSkipToothRemoval.execute` |  |

## [blender/ios_socket_boolean.py](../blender/ios_socket_boolean.py)

156 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 15 | `prepared` |  |
| 20 | `targets` |  |
| 25 | `applied` |  |
| 36 | `ready` |  |
| 46 | `apply` |  |
| 129 | `draw_closure` | Model step: the IOS only needs the hole closed; the Boolean comes later. |
| 141 | `draw_status` |  |

## [blender/ios_tooth_edit.py](../blender/ios_tooth_edit.py)

395 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 14 | `socket_depth_property` |  |
| 20 | `model` |  |
| 28 | `editing` |  |
| 33 | `immediate_ready` | IOS ready for the retentive model: tooth removed and hole closed inward. |
| 47 | `rim_loop` |  |
| 78 | `close_socket` | Native Grid Fill on the edit mesh; caller restores it if validation fails. |
| 175 | class `DSG_OT_IOSBeginToothRemoval` | `dsg.ios_begin_tooth_removal` · Seleccionar diente del IOS |
| 182 | `DSG_OT_IOSBeginToothRemoval.poll` |  |
| 185 | `DSG_OT_IOSBeginToothRemoval.execute` |  |
| 228 | class `DSG_OT_IOSCloseToothSocket` | `dsg.ios_close_tooth_socket` · Cerrar hueco hacia dentro |
| 235 | `DSG_OT_IOSCloseToothSocket.poll` |  |
| 241 | `DSG_OT_IOSCloseToothSocket.execute` |  |
| 292 | class `DSG_OT_IOSCancelToothRemoval` | `dsg.ios_cancel_tooth_removal` · Cancelar edición del diente |
| 298 | `DSG_OT_IOSCancelToothRemoval.poll` |  |
| 301 | `DSG_OT_IOSCancelToothRemoval.execute` |  |
| 324 | class `DSG_OT_IOSRetrySocketBoolean` | `dsg.ios_retry_socket_boolean` · Reintentar booleana después del cierre |
| 330 | `DSG_OT_IOSRetrySocketBoolean.poll` |  |
| 336 | `DSG_OT_IOSRetrySocketBoolean.execute` |  |
| 352 | `draw` |  |

## [blender/live_relief.py](../blender/live_relief.py)

275 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 45 | `_guide` |  |
| 50 | `blockout` |  |
| 55 | `axis_local` |  |
| 67 | `editing` |  |
| 73 | `supports_live_retention` |  |
| 77 | `apply_retention` | Re-evaluate the blockout for a new retention value; False if not possible. |
| 111 | `on_retention_changed` |  |
| 116 | `_restore` | Put back the committed coordinates of the previous preview. |
| 131 | `preview` | Show the selected relief live; returns the number of vertices moved. |
| 172 | `commit` | Keep the previewed relief as part of the blockout; returns vertices fixed. |
| 188 | `on_local_relief_changed` |  |
| 193 | `run_audit` |  |
| 220 | `_audit_timer` |  |
| 226 | `schedule_audit` | (Re)start the countdown: the audit runs once the user stops changing. |
| 234 | `_poll` |  |
| 242 | `_step` |  |
| 262 | `status_text` |  |
| 267 | `register` |  |
| 272 | `unregister` |  |

## [blender/microscrew_safety.py](../blender/microscrew_safety.py)

118 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 9 | `screws` |  |
| 14 | `sync` |  |
| 55 | `contacts` |  |
| 67 | `validate` |  |
| 81 | `gate` |  |
| 93 | `needs_refresh` |  |
| 105 | `request_refresh` | Safe from Panel.draw: rebuilds missing/orphan safety cylinders later. |
| 112 | `refresh` |  |

## [blender/mpr_view.py](../blender/mpr_view.py)

225 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | `active` |  |
| 26 | `wanted` |  |
| 34 | `_keep` | Objects that stay as they are in MPR view. |
| 50 | `_ghost_material` |  |
| 71 | `_bones` |  |
| 77 | `_show_ghost` |  |
| 104 | `_hide_ghost` |  |
| 110 | `_show_neighbours` |  |
| 124 | `enter` |  |
| 140 | `leave` |  |
| 154 | `sync` | Enter or leave the MPR view to match the review / implant planes. |
| 172 | `plane_object` |  |
| 176 | `plane_shown` |  |
| 181 | `any_shown` |  |
| 188 | `_set_plane` |  |
| 199 | class `DSG_OT_ToggleMPRPlane` | `dsg.toggle_mpr_plane` · Mostrar/ocultar MPR |
| 208 | `DSG_OT_ToggleMPRPlane.execute` |  |

## [blender/nerve_safety.py](../blender/nerve_safety.py)

186 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 15 | `capture_arch` |  |
| 23 | `required` |  |
| 30 | `margin` |  |
| 37 | `changed` |  |
| 43 | `register` |  |
| 49 | `unregister` |  |
| 54 | `clear` |  |
| 59 | `_convex_proxy` | Closed conservative outer envelope, without modifying the source mesh. |
| 74 | `_geometry` |  |
| 104 | `measure` |  |
| 116 | `measure.nearest` |  |
| 123 | `failures` |  |
| 144 | `description` |  |
| 158 | `draw` |  |

## [blender/optimizer_diagnostics.py](../blender/optimizer_diagnostics.py)

80 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `diagnose` |  |
| 7 | `diagnose.add` |  |

## [blender/optional_next.py](../blender/optional_next.py)

67 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `call` |  |
| 10 | `advance` |  |
| 53 | class `DSG_OT_OptionalNext` | `dsg.optional_next` · SIGUIENTE |
| 59 | `DSG_OT_OptionalNext.execute` |  |

## [blender/organic_curve.py](../blender/organic_curve.py)

163 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `handles` |  |
| 19 | `evaluate` |  |
| 25 | `route_distance` |  |
| 35 | `adaptive_controls` |  |
| 92 | `circular_gaussian` | Low-pass filter on a closed loop (wraps around the seam). |
| 106 | `least_bending_in_tube` | Smoothest closed curve within ``limit`` mm of ``route``. |
| 124 | `_resample_closed` |  |
| 135 | `smooth_route` | Smooth, even centreline from the dense geodesic route. |

## [blender/organic_frame.py](../blender/organic_frame.py)

56 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `build` |  |

## [blender/progress_overlay.py](../blender/progress_overlay.py)

272 líneas · imports Blender: blf, bpy, gpu

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 23 | `active` |  |
| 27 | `visible` |  |
| 31 | `begin` |  |
| 48 | `step` | Start a new stage at ``pct`` percent. |
| 58 | `update` | Progress report: a new phase opens a step, the same phase only |
| 74 | `_after_change` |  |
| 86 | `end` |  |
| 112 | `_clear` |  |
| 121 | `draw_bar` | Percentage bar for the panel; returns True when something was drawn. |
| 135 | `_status` |  |
| 144 | `_tag_redraw` |  |
| 153 | `_redraw` |  |
| 167 | `_install` |  |
| 172 | `_remove` |  |
| 182 | `_elapsed` |  |
| 187 | `_lines` |  |
| 214 | `_draw` |  |
| 265 | `unregister` |  |

## [blender/protected_neighbors.py](../blender/protected_neighbors.py)

322 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 11 | `extraction` |  |
| 16 | `teeth` |  |
| 21 | `kept` | Neighbours the clinician chose to SEE.  None by default: showing every |
| 31 | `canals` |  |
| 40 | `lower` |  |
| 57 | `_desired` | Visibility plan for the guide steps, or None when it does not apply. |
| 90 | `_models` | (object, shown) pairs for the socket view and the extension preview. |
| 111 | `_apply` |  |
| 135 | `sync` | Apply neighbour/nerve visibility. Never call it from Panel.draw. |
| 142 | `needs_sync` |  |
| 157 | `request_sync` | Safe from Panel.draw: schedules sync only when something differs. |
| 164 | class `DSG_OT_ToggleProtectedNeighbor` | `dsg.toggle_protected_neighbor` · Conservar diente vecino |
| 171 | `DSG_OT_ToggleProtectedNeighbor.execute` |  |
| 186 | class `DSG_OT_EditProtectedNeighbors` | `dsg.edit_protected_neighbors` · ELEGIR DIENTES VECINOS |
| 190 | `DSG_OT_EditProtectedNeighbors.execute` |  |
| 195 | class `DSG_OT_ResetProtectedNeighbors` | `dsg.all_protected_neighbors` · MOSTRAR TODOS LOS VECINOS |
| 200 | `DSG_OT_ResetProtectedNeighbors.execute` |  |
| 208 | class `DSG_OT_ClearProtectedNeighbors` | `dsg.clear_protected_neighbors` · QUITAR DIENTES VECINOS |
| 214 | `DSG_OT_ClearProtectedNeighbors.execute` |  |
| 220 | class `DSG_OT_ConfirmProtectedNeighbors` | `dsg.confirm_protected_neighbors` · CONFIRMAR SELECCIÓN |
| 226 | `DSG_OT_ConfirmProtectedNeighbors.execute` |  |
| 233 | class `DSG_OT_ReopenProtectedNeighbors` | `dsg.reopen_protected_neighbors` · Cambiar dientes vecinos |
| 238 | `DSG_OT_ReopenProtectedNeighbors.execute` |  |
| 243 | `confirmed` |  |
| 249 | `_toggles` |  |
| 265 | `_nerve` |  |
| 272 | `draw_step` | Neighbour step before implant placement; True once the selection is confirmed. |
| 295 | `draw` |  |

## [blender/relationship_lines.py](../blender/relationship_lines.py)

43 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `hide_all` | Turn the relationship-line overlay off in every 3D view of every screen. |
| 23 | `_deferred` |  |
| 29 | `on_load` |  |
| 33 | `register` |  |
| 39 | `unregister` |  |

## [blender/retention_finish.py](../blender/retention_finish.py)

45 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `run` |  |
| 28 | class `DSG_OT_PrepareRetentionUnified` | `dsg.prepare_retention_unified` · PREPARAR MODELO RETENTIVO |
| 34 | `DSG_OT_PrepareRetentionUnified.execute` |  |

## [blender/rim_smooth.py](../blender/rim_smooth.py)

122 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 24 | `coordinate_key` |  |
| 28 | `_face_normals` |  |
| 32 | `_band_by_distance` | Vertices reachable from the border within ``limit`` (Euclidean). |
| 59 | `smooth` | Smooth the border band in place; returns (released_keys, diagnostics). |

## [blender/safety_alerts.py](../blender/safety_alerts.py)

134 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `contact_label` |  |
| 25 | `active` |  |
| 29 | `observe` |  |
| 54 | `_display_ready` |  |
| 58 | `_show_popup` |  |
| 61 | `_show_popup.draw` |  |
| 70 | `_dispatch` |  |
| 92 | `_timer` |  |
| 96 | class `DSG_OT_ShowSafetyContacts` | `dsg.show_safety_contacts` · ALERTA DE SEGURIDAD |
| 101 | `DSG_OT_ShowSafetyContacts.execute` |  |
| 110 | `draw_warning` |  |
| 119 | `clear` |  |
| 124 | `register` |  |
| 130 | `unregister` |  |

## [blender/safety_volume.py](../blender/safety_volume.py)

311 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 19 | `visible` |  |
| 53 | `sync` |  |
| 79 | `obstacles` |  |
| 89 | `contacts` |  |
| 102 | `_mesh_arrays` |  |
| 114 | `_local_geometry` | Obstacle geometry in its own local space, cached while the mesh is unchanged. |
| 137 | `_inside` | Ray parity: is ``origin`` inside the closed surface held by ``tree``? |
| 149 | `mesh_contacts` |  |
| 177 | `gate` |  |
| 197 | `remember` |  |
| 203 | `update` |  |
| 228 | `_audit_timer` | Warn on a settled editing pose; never overwrite Blender's native R/G. |
| 270 | `load` |  |
| 283 | `register` |  |
| 296 | `unregister` |  |

## [blender/segmentation_finish.py](../blender/segmentation_finish.py)

193 líneas · imports Blender: bmesh, bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 13 | `targets` |  |
| 24 | `in_scope` |  |
| 31 | `reset` |  |
| 36 | `closed` |  |
| 45 | `rollback` |  |
| 79 | `complete` |  |
| 97 | `start` |  |
| 152 | `cancel_before_alignment` |  |
| 158 | class `DSG_OT_FinishSegmentedTeeth` | `dsg.finish_segmented_teeth` · Mejorar dientes |
| 165 | `DSG_OT_FinishSegmentedTeeth.poll` |  |
| 170 | `DSG_OT_FinishSegmentedTeeth.execute` |  |
| 183 | `draw` |  |

## [blender/socket_reach.py](../blender/socket_reach.py)

186 líneas · imports Blender: bmesh, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 18 | `_world` |  |
| 26 | `occlusal_direction` |  |
| 37 | `plan_extension` | Axial shift per cutter vertex (pure NumPy); zeros when already open. |
| 59 | `requirement` | Extension needed for the root section to come out of the IOS. |
| 96 | `extend` | Extrude the coronal cross-section by the chosen physical length. |
| 145 | `cutter_tree` | World-space BVH of a cutter, kept to verify the socket after cleanup. |
| 157 | `verify_opening` | Socket open to the outside and as deep as the tooth, without rays. |

## [blender/surface_clearance_bounds.py](../blender/surface_clearance_bounds.py)

43 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `classify` | Bounds the distance over whole faces, including edge/face interiors. |
| 20 | `classify.add` |  |

## [blender/upper_cavity_job.py](../blender/upper_cavity_job.py)

74 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 9 | `on_load` |  |
| 11 | `source_signature` |  |
| 15 | `input_path` |  |
| 23 | `stop` |  |
| 32 | `start` |  |
| 51 | `poll` |  |

## [blender/upper_cavity_safety.py](../blender/upper_cavity_safety.py)

409 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 25 | `objects` |  |
| 32 | `signature` |  |
| 41 | `reviewed` |  |
| 52 | `confirm` |  |
| 72 | `_orientation` | +1 when the zone's triangles wind outward (positive volume), else -1. |
| 81 | `_points` |  |
| 88 | `penetration` | (depth inside the zone, clearance outside it) in mm, implant surface vs zone surface. |
| 129 | `_limits` |  |
| 136 | `failures` | Blocking zones only (nasal invasion, sinus > limit, unmeasurable). |
| 167 | `report` |  |
| 172 | `alerts` |  |
| 177 | `description` |  |
| 185 | `import_surfaces` |  |
| 216 | class `DSG_OT_PrepareUpperCavities` | `dsg.prepare_upper_cavities` · IDENTIFICAR SENOS Y CAVIDAD NASAL |
| 219 | `DSG_OT_PrepareUpperCavities.execute` |  |
| 226 | class `DSG_OT_ReviewUpperCavities` | `dsg.review_upper_cavities` · REVISAR SENOS Y CAVIDAD NASAL |
| 229 | `DSG_OT_ReviewUpperCavities.execute` |  |
| 235 | class `DSG_OT_ConfirmUpperCavities` | `dsg.confirm_upper_cavities` · CONFIRMAR CAVIDADES SUPERIORES |
| 240 | `DSG_OT_ConfirmUpperCavities.invoke` |  |
| 241 | `DSG_OT_ConfirmUpperCavities.execute` |  |
| 249 | class `DSG_OT_AssignUpperCavity` | `dsg.assign_upper_cavity` · ASIGNAR MALLA DE CAVIDAD |
| 253 | `DSG_OT_AssignUpperCavity.invoke` |  |
| 254 | `DSG_OT_AssignUpperCavity.execute` |  |
| 268 | `changed` |  |
| 278 | `_stage_watch` | Hide the zones while aligning (3 points), restore them afterwards. |
| 297 | `register` |  |
| 314 | `unregister` |  |
| 329 | `_material` |  |
| 349 | `_show_zones` |  |
| 358 | `style` |  |
| 367 | `draw_toggle` | Compact visibility row for the segmented danger zones (any step). |
| 376 | `draw` | Danger zones of the upper arch: one line per zone, live while placing. |

## [blender/virtual_extraction.py](../blender/virtual_extraction.py)

305 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | `required` |  |
| 27 | `targets` |  |
| 32 | `done` |  |
| 39 | `performed` |  |
| 43 | `confirmed` |  |
| 47 | `teeth` |  |
| 52 | `bones_for` | Bone meshes that should receive the socket (plain bone and composite). |
| 70 | `_closed` | Every edge shared by exactly two faces (vectorised; bone meshes are big). |
| 80 | `_carve_bone` | MANIFOLD-only difference: fast, and skipped when the bone is not solid. |
| 112 | `_hide_tooth` |  |
| 129 | `_show_tooth` |  |
| 141 | class `DSG_OT_PerformVirtualExtraction` | `dsg.perform_virtual_extraction` · REALIZAR OPERACIÓN BOOLEANA |
| 148 | `DSG_OT_PerformVirtualExtraction.execute` |  |
| 222 | class `DSG_OT_ConfirmVirtualExtraction` | `dsg.confirm_virtual_extraction` · SIGUIENTE |
| 228 | `DSG_OT_ConfirmVirtualExtraction.execute` |  |
| 241 | class `DSG_OT_UndoVirtualExtraction` | `dsg.undo_virtual_extraction` · Restaurar diente |
| 247 | `DSG_OT_UndoVirtualExtraction.execute` |  |
| 271 | `draw` | Draw the sub-step; returns True once SIGUIENTE was pressed. |

## [blender_compat.py](../blender_compat.py)

46 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | `runtime_report` |  |
| 35 | `assert_supported_runtime` |  |

## [bone_interpretation.py](../bone_interpretation.py)

21 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `requires_bone_review` |  |
| 15 | `interpret_search_result` |  |

## [cbct_dental_module.py](../cbct_dental_module.py)

2857 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 38 | `_np` |  |
| 43 | `_ensure_child_collection` |  |
| 60 | `_unlink_from_other_collections` |  |
| 69 | `_delete_object` |  |
| 86 | `clear_dentition` |  |
| 118 | `_tooth_labels_present` |  |
| 132 | `_labelmap_cache_key` |  |
| 142 | `_bbox_slices` | Return one bbox per integer label, cached for the current labelmap. |
| 158 | `_expanded_bbox_bounds` |  |
| 167 | `correct_universal_semantics` | Validate arch first, then laterality, in DICOM patient coordinates. |
| 180 | `correct_universal_mirroring` | Compatibility wrapper for callers that explicitly request laterality only. |
| 193 | `_clean_tooth_mask` | Materialize one safe tooth component without ever merging large islands. |
| 225 | `_prepare_mesh_from_label` | Native-resolution single-label fallback / explicit refinement path. |
| 327 | `_dentition_crop_bounds` |  |
| 346 | `prepare_universal_dentition_meshes` | Prepare all FDI surfaces at native resolution in one semantic pass. |
| 483 | `upgrade_teeth_to_full_resolution` | Promote only clinician-selected teeth to full CBCT-constrained meshes. |
| 559 | `_commit_prepared_tooth` | Fast Blender-only commit of one already prepared tooth mesh. |
| 655 | `_mesh_from_label` | Compatibility wrapper. New full workflow prepares arrays off-main-thread. |
| 668 | `_vector_prop` |  |
| 682 | `_tooth_world_vertices` |  |
| 690 | `_tooth_world_centroid` |  |
| 703 | `_fdi_arch_centres` |  |
| 727 | `_fdi_patient_superior_world` |  |
| 733 | `_fdi_patient_anterior_world` |  |
| 738 | `_fdi_tooth_coronal_world` |  |
| 759 | `_fdi_vestibular_direction` | Estimate buccal/facial direction from the learned dental arch geometry. |
| 783 | `_fdi_label_anchor_world` | Choose the facial surface of the coronal half of the segmented tooth. |
| 812 | `_fdi_label_anchor_world.score` |  |
| 823 | `_fdi_label_world_matrix` | Build a text frame: glyph Y=patient superior, glyph Z=vestibular. |
| 864 | `_create_fdi_label` | Create one compact FDI label on the facial crown surface. |
| 919 | `rebuild_fdi_labels` | Rebuild the FDI display overlay without owning clinical segmentation. |
| 981 | `set_alignment_visual_smoothing` | Toggle measured, volume-preserving surface offsets without remeshing. |
| 1005 | `set_dentition_alignment_visual_smoothing` |  |
| 1021 | `visual_smoothing_objects` | Include disposable CBCT references visible during IOS alignment. |
| 1035 | `visual_smoothing_enabled` |  |
| 1043 | class `DSG_OT_CBCTToggleSurfaceSmoothing` | `dsg.cbct_toggle_surface_smoothing` · Suavizar superficie CBCT |
| 1053 | `DSG_OT_CBCTToggleSurfaceSmoothing.poll` |  |
| 1056 | `DSG_OT_CBCTToggleSurfaceSmoothing.execute` |  |
| 1074 | `draw_surface_smoothing` |  |
| 1079 | `reset_scene_state` |  |
| 1095 | `dentition_objects` | Return tooth objects belonging to the current scene, not stale datablocks. |
| 1120 | `_labels_hidden_for_implant_review` |  |
| 1127 | `labels_visible` |  |
| 1134 | `labels_visible_for_arch` | Show FDI labels only for the CBCT arch used as alignment reference. |
| 1166 | `dental_runtime_contract_preflight` | Validate literals used by runtime-created dental assets. |
| 1182 | `native_alignment_code_preflight` | Cheap readiness test with no scene mutation. |
| 1191 | `_alignment_source_kind` |  |
| 1204 | `segmented_alignment_source_objects` | Return every current clinical CBCT segmentation mesh, never helpers. |
| 1263 | `_alignment_work_collection` |  |
| 1275 | `_delete_alignment_duplicate` |  |
| 1290 | `_duplicate_segmented_sources` | Create real Blender copies before composing the disposable target. |
| 1312 | `_segmentation_signature` |  |
| 1325 | `set_segmented_sources_alignment_visibility` | Show originals in DICOM; hide them while the two-object alignment is active. |
| 1342 | `clear_alignment_working_composite` |  |
| 1372 | `build_segmented_alignment_composite` | Duplicate every segmented CBCT mesh and merge the copies into one object. |
| 1552 | `_immediate_source_hidden` |  |
| 1561 | `_delete_named_mesh` |  |
| 1577 | `_join_immediate_arch_sources` | Duplicate and Ctrl+J one jaw with its visible teeth. |
| 1668 | `build_immediate_arch_composites` | Build the two socket-review models after the clinician hides teeth with H. |
| 1756 | `ensure_segmented_alignment_composite` |  |
| 1781 | `build_native_tooth_alignment_reference` |  |
| 1786 | `ensure_native_tooth_alignment_reference` |  |
| 1790 | `iter_build_universal_dentition` | Yield after each tooth so Blender can redraw between mesh creations. |
| 1953 | `build_universal_dentition` | Synchronous compatibility wrapper around the single dentition builder. |
| 1965 | `current_payload` |  |
| 1998 | class `DSGCBCTDentalProperties` |  |
| 2026 | `segmented_objects` | Every mesh produced by CBCT segmentation: teeth, jaws, canal, arches. |
| 2053 | `_remesh_source_mesh` | Original geometry: before any previous remesh and before smoothing. |
| 2065 | `_forget_smoothing_cache` |  |
| 2072 | `voxel_remesh_object` | Replace obj.data with a voxel remesh of its original mesh. |
| 2106 | `restore_voxel_remesh` |  |
| 2121 | class `DSG_OT_VoxelRemeshSegmented` | `dsg.voxel_remesh_segmented` · Remesh vóxel |
| 2128 | `DSG_OT_VoxelRemeshSegmented.poll` |  |
| 2132 | `DSG_OT_VoxelRemeshSegmented.execute` |  |
| 2163 | class `DSG_OT_VoxelRemeshRestore` | `dsg.voxel_remesh_restore` · Mallas originales |
| 2169 | `DSG_OT_VoxelRemeshRestore.execute` |  |
| 2178 | `draw_voxel_remesh` |  |
| 2194 | class `DSG_OT_CBCTAcceptFDI` | `dsg.cbct_accept_fdi` · Confirmar FDI |
| 2199 | `DSG_OT_CBCTAcceptFDI.execute` |  |
| 2306 | class `DSG_OT_CBCTImproveGeometry` | `dsg.cbct_improve_geometry` · Mejorar geometría |
| 2313 | `DSG_OT_CBCTImproveGeometry.poll` |  |
| 2321 | `DSG_OT_CBCTImproveGeometry.execute` |  |
| 2403 | class `DSG_OT_CBCTToggleFDI` | `dsg.cbct_toggle_fdi` · Mostrar/Ocultar FDI |
| 2408 | `DSG_OT_CBCTToggleFDI.execute` |  |
| 2415 | class `DSG_OT_CBCTEditFDI` | `dsg.cbct_edit_fdi` · Corregir FDI seleccionado |
| 2423 | `DSG_OT_CBCTEditFDI.poll` |  |
| 2427 | `DSG_OT_CBCTEditFDI.invoke` |  |
| 2432 | `DSG_OT_CBCTEditFDI.execute` |  |
| 2479 | class `DSG_OT_CBCTSwapArches` | `dsg.cbct_swap_arches` · Intercambiar maxilar / mandíbula |
| 2489 | `DSG_OT_CBCTSwapArches.poll` |  |
| 2492 | `DSG_OT_CBCTSwapArches.execute` |  |
| 2556 | class `DSG_OT_CBCTDeleteTooth` | `dsg.cbct_delete_tooth` · Marcar diente como ausente |
| 2562 | `DSG_OT_CBCTDeleteTooth.poll` |  |
| 2566 | `DSG_OT_CBCTDeleteTooth.execute` |  |
| 2582 | `draw_review` |  |
| 2643 | `draw_alignment_handoff` |  |
| 2654 | class `DSG_OT_InstallAIRuntime` | `dsg.install_ai_runtime` · Instalar motores de segmentación |
| 2661 | `DSG_OT_InstallAIRuntime.execute` |  |
| 2673 | class `DSG_OT_AIStatusRefresh` | `dsg.ai_status_refresh` · Revisar motores de segmentación |
| 2678 | `DSG_OT_AIStatusRefresh.execute` |  |
| 2694 | class `DSG_OT_CopyPipelineDiagnostic` | `dsg.copy_pipeline_diagnostic` · Copiar diagnóstico |
| 2698 | `DSG_OT_CopyPipelineDiagnostic.execute` |  |
| 2740 | `_cleanup_stale_registration` | Remove only this module's known RNA footprint before a fresh register. |
| 2759 | `migrate_existing_asset_metadata` | One-time compatible stamping for teeth saved by pre-v9 DSG scenes. |
| 2790 | `register` |  |
| 2824 | `deferred_post_register` | Run data-sensitive CBCT metadata migration after _RestrictData is gone. |
| 2841 | `unregister` |  |

## [cbct_native_threshold.py](../cbct_native_threshold.py)

698 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 32 | class `ThresholdBlockIndex` |  |
| 57 | class `ThresholdSurface` |  |
| 65 | `_padded_point_shape` |  |
| 75 | `_cpu_block_minmax` |  |
| 87 | `_reduce_parent_minmax` |  |
| 100 | `_try_prepare_cuda` |  |
| 118 | `_gpu_block_minmax` |  |
| 134 | `build_threshold_index` |  |
| 205 | `active_blocks` | Exact active leaf blocks: min <= level <= max. |
| 220 | `active_parent_blocks` |  |
| 226 | `_weld_by_quantization` |  |
| 244 | `_vtk_scalar_chunk` |  |
| 275 | `_prepare_vtk_zero_copy_cache` | Bind VTK directly to DSG's persistent float32 NumPy volume. |
| 311 | `_compact_remove_degenerate` |  |
| 333 | `extract_threshold_vtk_zero_copy` |  |
| 380 | `extract_threshold_vtk_hierarchy` |  |
| 453 | `_load_mc_classic_table` |  |
| 462 | `_torch_cuda_marching_cubes` | Exact native-grid Marching Cubes on CUDA using the classic case table. |
| 632 | `extract_threshold_surface` | Best available exact native-resolution threshold surface. |

## [cbct_pipeline_client.py](../cbct_pipeline_client.py)

271 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | `_tail` |  |
| 24 | `_json_geometry` |  |
| 39 | `_python_prefix` |  |
| 44 | `_creationflags` |  |
| 48 | `_launch_python_worker` |  |
| 60 | `_launch_blender_fallback` |  |
| 69 | `start_full_pipeline` |  |
| 104 | `state` |  |
| 167 | `snapshot_failure_diagnostics` | Persist redacted worker evidence before transactional cleanup. |
| 217 | `consume_manifest` |  |
| 227 | `diagnostic_text` | Copy only the structured run record, never private request/log contents. |
| 239 | `artifact_dir` |  |
| 242 | `release_process_keep_artifacts` |  |
| 253 | `cancel` |  |
| 266 | `cleanup_artifacts` |  |

## [cbct_pipeline_tasks.py](../cbct_pipeline_tasks.py)

338 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 21 | `_json_safe` |  |
| 32 | `_load_vtk` |  |
| 40 | `_load_measure` |  |
| 48 | `compact_mask_for_classes` |  |
| 73 | `_ellipsoid` | Binary morphology kernel in physical millimetres (Z,Y,X spacing). |
| 83 | `refine_single_source_canal` | Preserve the historical 0.65 mm canal closing without fake verification. |
| 117 | `global_voxel_to_xyz` |  |
| 127 | `_present_teeth` |  |
| 132 | `_bbox_slices` |  |
| 137 | `_dentition_bounds` |  |
| 150 | `prepare_tooth_meshes` |  |
| 204 | `_save_binary_surface` |  |
| 220 | `simple_arch_masks` | Return exactly two binary crops for the SIMPLE implant route. |
| 233 | `prepare_simple_arches_route_map` | Create SIMPLE surfaces from a minimal 1=upper / 2=lower route map. |
| 260 | `prepare_simple_arches` | Create only two native-resolution surfaces; no FDI meshes and no canal. |
| 288 | `run_teeth_task` | Prepare meshes from the normalized DSG compatibility labelmap. |
| 311 | `run_surfaces_task` |  |
| 334 | `run_task` |  |

## [cbct_pipeline_worker.py](../cbct_pipeline_worker.py)

732 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 29 | `atomic_json` |  |
| 46 | `bootstrap` |  |
| 77 | `_fdi_to_compat` |  |
| 90 | `_toothseg_class_to_fdi` |  |
| 103 | `_make_affine` |  |
| 127 | `_physical_fov_mm` |  |
| 131 | `_direct113_supported` |  |
| 138 | `_predict_totalseg_direct` |  |
| 160 | `_translate_totalseg` |  |
| 193 | `infer_totalseg` |  |
| 265 | `_find_model_folder` |  |
| 281 | `_predict_nnunet_folder` |  |
| 304 | `_resample_nifti_to_spacing` |  |
| 322 | `infer_toothseg` |  |
| 413 | `_load_module_from_file` |  |
| 423 | `_find_umamba_model` |  |
| 438 | `infer_umamba2` |  |
| 505 | `main` |  |
| 517 | `main.status` |  |
| 534 | `main.heartbeat` |  |
| 695 | `run_request` |  |

## [cbct_post_smoothing.py](../cbct_post_smoothing.py)

293 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 15 | `tooth_objects` |  |
| 18 | `mesh_arrays` |  |
| 24 | `source_mesh` |  |
| 28 | `mesh_hash` |  |
| 31 | `snapshot_object` |  |
| 36 | `active` |  |
| 39 | `busy` |  |
| 42 | `_disable_legacy` |  |
| 47 | `restore_originals` |  |
| 56 | `apply_cached` |  |
| 79 | `apply_result` |  |
| 130 | `_cleanup` |  |
| 135 | `cancel` |  |
| 151 | `cancel_on_load` |  |
| 153 | `_poll` |  |
| 189 | `start` |  |
| 239 | class `DSG_OT_PostSmoothTeeth` | `dsg.cbct_post_smooth_teeth` · Suavizar dientes |
| 244 | `DSG_OT_PostSmoothTeeth.poll` |  |
| 245 | `DSG_OT_PostSmoothTeeth.execute` |  |
| 253 | class `DSG_OT_CancelPostSmooth` | `dsg.cbct_cancel_post_smooth` · Cancelar suavizado |
| 256 | `DSG_OT_CancelPostSmooth.execute` |  |
| 258 | class `DSG_OT_PostSmoothReport` | `dsg.cbct_post_smooth_report` · Resultado del suavizado |
| 261 | `DSG_OT_PostSmoothReport.execute` |  |
| 263 | `DSG_OT_PostSmoothReport.execute.draw` |  |
| 271 | `draw` |  |
| 287 | `register_hooks` |  |
| 290 | `unregister_hooks` |  |

## [cbct_post_smoothing_worker.py](../cbct_post_smoothing_worker.py)

165 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `atomic_json` |  |
| 14 | `run` |  |
| 24 | `run.status` |  |
| 33 | `run.to_display` |  |

## [cbct_surface_meshing.py](../cbct_surface_meshing.py)

719 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 35 | class `SurfaceExtraction` |  |
| 48 | `_as_binary_u8` |  |
| 55 | `_sample_for_step` |  |
| 72 | `_configure_vtk_smp` | Enable a native VTK SMP backend when the wheel exposes one. |
| 113 | `_vtk_poly_to_arrays` |  |
| 139 | `_vtk_flying_edges` |  |
| 194 | `_skimage_lewiner` |  |
| 213 | `extract_binary_surface` | Extract an isosurface from one compact binary ROI. |
| 282 | class `LabelSurfaceExtraction` |  |
| 290 | class `MultiLabelSurfaceExtraction` |  |
| 301 | `_triangle_components` | Connected-component id per vertex, using triangle edges. |
| 332 | `_triangle_components.find` |  |
| 338 | `_triangle_components.union` |  |
| 356 | `clean_surface_components` | Keep only the dominant connected surface component. |
| 441 | `_vtk_multilabel_flying_edges` | Extract all requested semantic labels in one VTK pass at native resolution. |
| 654 | `extract_multilabel_surface` | Native-resolution multi-label extraction with deterministic fallback. |

## [cbct_surface_sidecar.py](../cbct_surface_sidecar.py)

76 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 16 | `_arg_job_path` |  |
| 25 | `main` |  |

## [cbct_surface_worker_client.py](../cbct_surface_worker_client.py)

82 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | `sidecar_requested` |  |
| 24 | `extract_multilabel_sidecar` |  |

## [cbct_upper_cavities.py](../cbct_upper_cavities.py)

59 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `merge_nasal` |  |
| 17 | `_infer_task` |  |
| 39 | `infer_nasal` |  |
| 43 | `infer_sinuses` |  |
| 48 | `prepare` |  |

## [cbct_upper_worker.py](../cbct_upper_worker.py)

36 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 6 | `main` |  |

## [clinical_context.py](../clinical_context.py)

530 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 33 | `_registry_path` |  |
| 37 | `load_source_registry` |  |
| 46 | `_load_scene_json` |  |
| 56 | `_store_scene_json` |  |
| 60 | `_scene_del` |  |
| 68 | `empty_patient_context` |  |
| 72 | `get_patient_clinical_context` |  |
| 78 | `set_patient_clinical_context` |  |
| 103 | `clear_patient_clinical_context` |  |
| 114 | `build_clinical_guidance_request` |  |
| 126 | `get_clinical_guidance_request` |  |
| 132 | `apply_clinical_guidance_result` |  |
| 148 | `get_clinical_guidance_result` |  |
| 154 | `confirm_clinical_review` |  |
| 168 | `clinical_summary` |  |
| 198 | `get_country_source_registry` |  |
| 221 | `build_medication_lookup_request` |  |
| 254 | class `DSGClinicalProperties` |  |
| 279 | class `DSG_OT_ClinicalSaveBasics` | `dsg.clinical_save_basics` · Guardar datos básicos |
| 284 | `DSG_OT_ClinicalSaveBasics.execute` |  |
| 299 | class `DSG_OT_ClinicalAddMedication` | `dsg.clinical_add_medication` · Añadir medicamento |
| 304 | `DSG_OT_ClinicalAddMedication.execute` |  |
| 331 | class `DSG_OT_ClinicalRemoveLastMedication` | `dsg.clinical_remove_last_medication` · Quitar último medicamento |
| 336 | `DSG_OT_ClinicalRemoveLastMedication.execute` |  |
| 346 | class `DSG_OT_ClinicalAddCondition` | `dsg.clinical_add_condition` · Añadir condición |
| 351 | `DSG_OT_ClinicalAddCondition.execute` |  |
| 365 | class `DSG_OT_ClinicalAddLab` | `dsg.clinical_add_lab` · Añadir analítica |
| 370 | `DSG_OT_ClinicalAddLab.execute` |  |
| 389 | class `DSG_OT_ClinicalCopyRequest` | `dsg.clinical_copy_request` · Copiar petición clínica MCP |
| 394 | `DSG_OT_ClinicalCopyRequest.execute` |  |
| 406 | class `DSG_OT_ClinicalConfirmReview` | `dsg.clinical_confirm_review` · Confirmar revisión clínica |
| 411 | `DSG_OT_ClinicalConfirmReview.execute` |  |
| 423 | class `DSG_OT_ClinicalClear` | `dsg.clinical_clear` · Borrar contexto clínico |
| 428 | `DSG_OT_ClinicalClear.execute` |  |
| 434 | class `DSG_PT_ClinicalContext` | `DSG_PT_clinical_context` · Paciente · Contexto clínico MCP |
| 442 | `DSG_PT_ClinicalContext.draw` |  |
| 517 | `register` |  |
| 523 | `unregister` |  |

## [clinical_core.py](../clinical_core.py)

430 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 72 | `_utc_now` |  |
| 76 | `_text` |  |
| 81 | `_finite_number` |  |
| 93 | `normalize_country_code` |  |
| 106 | `normalize_medication` |  |
| 132 | `normalize_condition` |  |
| 153 | `normalize_lab` |  |
| 173 | `normalize_patient_context` |  |
| 216 | `canonical_json` |  |
| 220 | `context_hash` |  |
| 227 | `_matches` |  |
| 232 | `infer_guidance_topics` |  |
| 240 | `infer_guidance_topics.add` |  |
| 285 | `missing_information` |  |
| 304 | `build_guidance_request` |  |
| 351 | `validate_guidance_result` |  |
| 391 | `validate_guidance_result.clean_claims` |  |

## [common_surface_match.py](../common_surface_match.py)

1503 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 46 | `_valid_mesh` |  |
| 51 | `_world_vertices` |  |
| 55 | `_world_normal_matrix` |  |
| 62 | `_world_face_normal` |  |
| 69 | `_build_face_adjacency` | Index-stable edge adjacency with a vectorized manifold fast path. |
| 127 | `_connected_components` |  |
| 145 | `_expanded_bounds` |  |
| 156 | `_inside_bounds` |  |
| 163 | `_reference_bvh` |  |
| 178 | `_reference_surface_data` | Combined reference surface, optionally restricted to the IOS-visible crown. |
| 315 | `_curvature_signatures` |  |
| 333 | `_curvature_similarity` |  |
| 343 | `_orient_normals_locally` | Return a locally coherent copy of the normal field on *faces*. |
| 377 | `_dijkstra_face_path` | Shortest weighted face path inside *allowed* or [] when disconnected. |
| 420 | `_connect_barrier_components` | Connect fragmented valley seeds with low-cost paths inside contact corridor. |
| 427 | `_connect_barrier_components.components` |  |
| 491 | `_signed_face_curvature` | Estimate signed mean curvature from the normal field on face centres. |
| 517 | `_negative_curvature_contact_barrier` | Return a continuous, locally oriented interproximal stop barrier. |
| 587 | `_fill_confidence_gaps` |  |
| 608 | `_mesh_boundary_faces` | Return face indices touching a true open edge of the IOS mesh. |
| 635 | `_fill_topological_pinhole_gaps` | Fill black pinholes/narrow channels without performing a blind Select More. |
| 683 | `_fill_enclosed_selection_holes` | Fill every reasonably sized unselected island completely enclosed by selection. |
| 746 | `_solidify_common_surface_selection` | Close selection pinholes and enclosed voids while preserving outer border. |
| 765 | `_trim_weak_spikes` |  |
| 780 | `_face_samples` |  |
| 798 | `_score_face` | Score one IOS face using reciprocal surface correspondence + context. |
| 848 | `_write_scores` |  |
| 862 | `write_scores` |  |
| 870 | `_world_coordinates` |  |
| 879 | `build_local_proxy` | World-space copy of only the faces of ``obj`` near ``focus_objects``. |
| 932 | `remove_local_proxy` |  |
| 941 | `remap_result_to_source` | Translate proxy face indices in a selection result back to the IOS. |
| 950 | `_select_components` |  |
| 974 | `_grow_coherent_surface` |  |
| 998 | `_build_object_bvh` |  |
| 1011 | `_bone_guard_face_set` | Reject IOS faces whose geometry is better explained by alveolar bone. |
| 1053 | `select_anatomy_locked_ios_seed` | Recover a difficult match without turning proximity into tooth identity. |
| 1302 | `select_common_ios_surface` | Precision-first common-surface matcher for immediate extraction review. |
| 1479 | `apply_common_surface_selection` | Persist a generated selection as both edit-state and vertex group. |

## [compute_probe.py](../compute_probe.py)

47 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `probe` |  |
| 32 | `main` |  |

## [core.py](../core.py)

4314 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 69 | `_is_dicom_collection` |  |
| 74 | `_walk_layer_collections` |  |
| 80 | `set_dicom_collections_hidden` | Hide/reveal complete DICOM collections and their view-layer nodes. |
| 157 | `language_code` |  |
| 163 | `is_spanish` |  |
| 167 | `tr` |  |
| 174 | `translate_ui` | Translate shared UI labels; Spanish remains the complete source locale. |
| 197 | `role_of` |  |
| 203 | `set_role` |  |
| 213 | `find_role` |  |
| 222 | `antagonist_objects` | Return persistent opposing-arch meshes, never inferred from visibility. |
| 232 | `bind_antagonists_to_source` | Parent the antagonist to the moving IOS while preserving world pose. |
| 250 | `find_alignment_reference` |  |
| 265 | `infer_stage` |  |
| 276 | `_workflow_mesh` | Return a live mesh referenced by a workflow Scene key, if any. |
| 286 | `reconcile_workflow_after_undo` | Repair only stale route pointers after Blender restores an undo snapshot. |
| 348 | `_run_workflow_undo_repair` |  |
| 359 | `dsg_workflow_undo_post` | Defer route reconciliation until Blender has finished swapping undo data. |
| 374 | `_register_workflow_undo_handler` |  |
| 380 | `_unregister_workflow_undo_handler` |  |
| 390 | `_is_dicom_related_object` |  |
| 411 | `prepare_guide_entry_view` |  |
| 465 | `_sync_danger_zones_for_stage` | Sinus and nasal zones are hidden while aligning (they cover the teeth |
| 488 | `set_stage` |  |
| 508 | `stage_is` |  |
| 513 | `language_get` |  |
| 519 | `language_set` |  |
| 529 | `clinical_route` |  |
| 538 | `target_fdi` |  |
| 553 | `route_requires_individual_teeth` |  |
| 557 | `_restore_virtual_extraction_if_needed` |  |
| 590 | `_workflow_route_update` |  |
| 608 | `_target_fdi_update` |  |
| 627 | class `DSGSuiteSettings` |  |
| 668 | `patient_folder` |  |
| 677 | `_set_patient_folder` |  |
| 694 | `_iter_dicom_candidate_paths` | Yield likely DICOM files without building/sorting a huge recursive list. |
| 731 | `_discover_patient_dicom` |  |
| 753 | `_start_patient_cbct_from_probe` |  |
| 783 | `_load_patient_cbct` |  |
| 791 | `_ios_arch_hint` |  |
| 802 | `_patient_ios_candidates` |  |
| 829 | `_patient_ios_candidates.score` |  |
| 840 | `_auto_import_patient_ios` |  |
| 916 | `_export_object_to_patient` |  |
| 953 | `_hidden_immediate_teeth` |  |
| 968 | class `DSG_SUITE_OT_ChoosePatientFolder` | `dsg_suite.choose_patient_folder` · Elegir paciente |
| 982 | `DSG_SUITE_OT_ChoosePatientFolder.invoke` |  |
| 989 | `DSG_SUITE_OT_ChoosePatientFolder.execute` |  |
| 1002 | `DSG_SUITE_OT_ChoosePatientFolder.execute.discover` |  |
| 1026 | `DSG_SUITE_OT_ChoosePatientFolder._finish` |  |
| 1034 | `DSG_SUITE_OT_ChoosePatientFolder.modal` |  |
| 1056 | `DSG_SUITE_OT_ChoosePatientFolder.cancel` |  |
| 1060 | class `DSG_SUITE_OT_LoadPatientCBCT` | `dsg_suite.load_patient_cbct` · Cargar CBCT del paciente |
| 1064 | `DSG_SUITE_OT_LoadPatientCBCT.execute` |  |
| 1074 | class `DSG_SUITE_OT_ChangeRoute` | `dsg_suite.change_route` · Cambiar ruta |
| 1080 | `DSG_SUITE_OT_ChangeRoute.execute` |  |
| 1135 | `_clear_dicom_route_checkpoint` |  |
| 1150 | `capture_dicom_route_checkpoint` | Snapshot generated DICOM geometry + UI state before a route starts. |
| 1191 | `restore_dicom_route_checkpoint` | Restore the exact generated-DICOM state captured before segmentation. |
| 1238 | class `DSG_SUITE_OT_StartSimpleRoute` | `dsg_suite.start_simple_route` · Implante simple |
| 1245 | `DSG_SUITE_OT_StartSimpleRoute.poll` |  |
| 1252 | `DSG_SUITE_OT_StartSimpleRoute.execute` |  |
| 1279 | class `DSG_SUITE_OT_ConfirmSimpleSTL` | `dsg_suite.confirm_simple_stl` · Confirmar arcadas y alinear |
| 1285 | `DSG_SUITE_OT_ConfirmSimpleSTL.execute` |  |
| 1307 | `_immediate_route_readiness` | Cheap route gate. Never imports Torch/nnU-Net in foreground Blender. |
| 1371 | class `DSG_SUITE_OT_StartImmediateRoute` | `dsg_suite.start_immediate_route` · Implante inmediato |
| 1378 | `DSG_SUITE_OT_StartImmediateRoute.poll` |  |
| 1394 | `DSG_SUITE_OT_StartImmediateRoute.execute` |  |
| 1435 | `DSG_SUITE_OT_StartImmediateRoute.execute._deferred_launch` |  |
| 1501 | class `DSG_SUITE_OT_AcceptFDIAndSelectTeeth` | `dsg_suite.accept_fdi_select_teeth` · FDI correcto · elegir dientes |
| 1506 | `DSG_SUITE_OT_AcceptFDIAndSelectTeeth.execute` |  |
| 1567 | class `DSG_SUITE_OT_FixImmediateExtractionSelection` | `dsg_suite.fix_immediate_extraction_selection` · Fijar dientes de extracción |
| 1575 | `DSG_SUITE_OT_FixImmediateExtractionSelection.execute` |  |
| 1603 | class `DSG_SUITE_OT_BuildImmediateArchModels` | `dsg_suite.build_immediate_arch_models` · Siguiente · crear modelos alveolares |
| 1609 | `DSG_SUITE_OT_BuildImmediateArchModels.execute` |  |
| 1668 | class `DSG_SUITE_OT_ConfirmImmediateModels` | `dsg_suite.confirm_immediate_models` · Confirmar |
| 1673 | `DSG_SUITE_OT_ConfirmImmediateModels.execute` |  |
| 1720 | `_immediate_extraction_fdis` | Return the clinician-selected immediate-extraction FDI values. |
| 1729 | `_immediate_cbct_teeth` |  |
| 1738 | `_immediate_neighbour_teeth` | Return only the external FDI neighbours of each extraction block. |
| 1765 | `_immediate_neighbour_teeth.add` |  |
| 1822 | `_immediate_active_jaw_bone` | Return the separate CBCT jaw surface used as buccal/lingual negative evidence. |
| 1839 | `_simple_split_two_large_jaw_islands` | Create maxilla/mandible display copies from the two largest loose islands. |
| 1886 | `_simple_split_two_large_jaw_islands.rank` |  |
| 1912 | `_simple_split_two_large_jaw_islands.mean_world_z` |  |
| 1941 | class `DSG_SUITE_OT_PrepareIOSPostExtraction` | `dsg_suite.prepare_ios_postextraction` · Preparar selección IOS postextracción |
| 1949 | `DSG_SUITE_OT_PrepareIOSPostExtraction.execute` |  |
| 2131 | `_clean_postextraction_boolean_debris` | Remove disconnected Boolean debris before the anatomy-safe base closure. |
| 2212 | `_edge_components_for_local_closure` | Return connected boundary-edge components without touching coordinates. |
| 2233 | `_bmesh_face_neighbours` |  |
| 2242 | `_solidify_local_extraction_selection_bmesh` | Fill internal selection voids before deleting the IOS crown. |
| 2371 | `_ordered_cycle_vertices_for_local_closure` | Return an ordered simple cycle for a degree-2 boundary component. |
| 2416 | `_exact_close_simple_edge_loop` | Close a simple boundary cycle deterministically, preserving every edge. |
| 2495 | `_local_open_components_from_seeds` | Find actual residual local hole loops, including fill-created edges. |
| 2510 | `_regularize_local_extraction_faces` | Trim only unsafe boundary faces until the extraction perimeter is cyclic. |
| 2587 | `_delete_selected_ios_region_and_close_local_openings` | Delete reviewed IOS crown faces and close only the newly created opening. |
| 2677 | `_delete_selected_ios_region_and_close_local_openings.open_tracked_edges` |  |
| 2831 | `_mesh_topology_counts` |  |
| 2845 | `extraction_smoothing_wanted` | Smoothing of the tooth to extract (on unless the clinician turns it off). |
| 2850 | `tooth_smoothing_state` | True when the measured surface smoothing is shown on this tooth. |
| 2862 | `ensure_extraction_smoothing` | Apply (or remove) the smoothing on the tooth to extract so that the |
| 2879 | `_tooth_cutter_source` | Mesh the extraction cutter is built from: the smoothed shape if the |
| 2907 | `_prepare_alveolar_cutter` | Watertight, pulp-free, slightly dilated copy of a CBCT tooth. |
| 2971 | `_remove_cutter` |  |
| 2980 | `_apply_alveolar_boolean` | Difference on two closed solids; MANIFOLD first, EXACT as fallback. |
| 3015 | `_track_postextraction_intermediate` |  |
| 3027 | class `DSG_SUITE_OT_ConfirmIOSPostExtraction` | `dsg_suite.confirm_ios_postextraction` · Confirmar IOS postextracción |
| 3035 | `DSG_SUITE_OT_ConfirmIOSPostExtraction.execute` |  |
| 3174 | class `DSG_SUITE_OT_RestoreIOSPreExtraction` | `dsg_suite.restore_ios_preextraction` · Restaurar IOS preextracción |
| 3180 | `DSG_SUITE_OT_RestoreIOSPreExtraction.execute` |  |
| 3215 | `_remove_object_and_data` | Remove one generated Blender object and orphaned local datablock safely. |
| 3235 | `_clear_immediate_review_geometry` | Clear only immediate-route review composites, never the raw CBCT volume. |
| 3262 | class `DSG_SUITE_OT_RecoverImmediateInputs` | `dsg_suite.recover_immediate_inputs` · Recover Immediate Inputs |
| 3270 | `DSG_SUITE_OT_RecoverImmediateInputs.execute` |  |
| 3291 | `_reset_guide_stage_internal` | Reset only DSG guide outputs while preserving the aligned IOS input. |
| 3306 | `_reset_alignment_stage_internal` | Reset alignment-generated state, preserving CBCT reference and IOS input. |
| 3333 | `_clear_dicom_route_outputs` | Return DICOM to a clean route-choice state while preserving loaded volume. |
| 3398 | `_back_from_dicom` | Deterministic clinical Back for the DICOM branch, never Blender Undo. |
| 3458 | class `DSG_SUITE_OT_BackWorkflow` | `dsg_suite.back_workflow` · Atrás |
| 3464 | `DSG_SUITE_OT_BackWorkflow.execute` |  |
| 3519 | class `DSG_SUITE_OT_RestartDICOM` | `dsg_suite.restart_dicom` · Reiniciar DICOM |
| 3525 | `DSG_SUITE_OT_RestartDICOM.invoke` |  |
| 3528 | `DSG_SUITE_OT_RestartDICOM.execute` |  |
| 3550 | class `DSG_SUITE_OT_RestartAlignment` | `dsg_suite.restart_alignment` · Reiniciar alineamiento |
| 3556 | `DSG_SUITE_OT_RestartAlignment.invoke` |  |
| 3559 | `DSG_SUITE_OT_RestartAlignment.execute` |  |
| 3575 | class `DSG_SUITE_OT_RestartDSG` | `dsg_suite.restart_dsg` · Reiniciar DSG |
| 3581 | `DSG_SUITE_OT_RestartDSG.invoke` |  |
| 3584 | `DSG_SUITE_OT_RestartDSG.execute` |  |
| 3598 | `set_status_bar` | Send contextual guidance/data to Blender's bottom status bar. |
| 3619 | `_stage_available` |  |
| 3639 | `_draw_vertical_stage_rail` | Three permanent stage buttons, stacked vertically on the left. |
| 3661 | class `DSG_SUITE_PT_WorkflowControls` | `DSG_SUITE_PT_workflow_controls` · Control del flujo |
| 3671 | `DSG_SUITE_PT_WorkflowControls.poll` |  |
| 3674 | `DSG_SUITE_PT_WorkflowControls.draw` |  |
| 3710 | class `DSG_SUITE_OT_SetStage` | `dsg_suite.set_stage` · Open module |
| 3717 | `DSG_SUITE_OT_SetStage.execute` |  |
| 3749 | class `DSG_SUITE_OT_UseSelectedIOS` | `dsg_suite.use_selected_ios` · Use selected IOS |
| 3754 | `DSG_SUITE_OT_UseSelectedIOS.execute` |  |
| 3781 | class `DSG_SUITE_OT_ToggleAntagonist` | `dsg_suite.toggle_antagonist` · Toggle Antagonist |
| 3787 | `DSG_SUITE_OT_ToggleAntagonist.execute` |  |
| 3805 | class `DSG_SUITE_PT_Main` | `DSG_SUITE_PT_main` · DSG |
| 3813 | `DSG_SUITE_PT_Main.draw` |  |
| 4109 | class `DSG_SUITE_OT_InstallEnginesCore` | `dsg_suite.install_engines_core` ·  |
| 4122 | `DSG_SUITE_OT_InstallEnginesCore.execute` |  |
| 4188 | `_core_unregister_class_object` |  |
| 4198 | `_core_unregister_stale_classes` | Release RNA classes left by an older DSG core before an in-place update. |
| 4213 | `_core_remove_stale_scene_pointer` |  |
| 4226 | `external_agent_execution_context` | Return the active Mixar agent context, if this call is running inside it. |
| 4248 | `reject_external_agent_for_user_gate` | Fail closed when a protected DSG operation is invoked by Mixar's agent. |
| 4270 | `register` |  |
| 4303 | `unregister` |  |

## [danger_zones.py](../danger_zones.py)

52 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 25 | `is_sinus` |  |
| 29 | `classify` | Status and message for one zone. |
| 51 | `_free` |  |

## [dental_asset_blender.py](../dental_asset_blender.py)

554 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 24 | `_known_role` |  |
| 31 | `stamp_object` | Stamp one Blender object with the canonical dental-family identity. |
| 94 | `object_role` |  |
| 100 | `object_family_id` |  |
| 106 | `object_fdi` |  |
| 117 | `object_coordinate_space` |  |
| 123 | `is_family_object` |  |
| 142 | `validate_object_contract` | Fail-fast validation of one persisted dental asset. |
| 247 | `find_family_members` |  |
| 261 | `find_one` |  |
| 266 | `migrate_legacy_tooth_object` | Stamp an existing pre-contract DSG tooth without renaming it. |
| 287 | `stamp_landmark_confidence` |  |
| 295 | `migrate_legacy_landmark_object` | Explicit import/scene migration for the two published legacy aliases. |
| 334 | `ensure_landmark_collection` |  |
| 345 | `_set_world_position_preserving_parent` |  |
| 358 | `store_mapping_metadata` |  |
| 373 | `read_mapping_metadata` |  |
| 386 | `apply_recognition_payload` | Materialize canonical landmark empties from a recognition payload. |
| 442 | `ensure_point_int_attribute` | Create/update the canonical POINT/INT attribute used for EOFF labels. |
| 466 | `read_point_int_attribute` |  |
| 480 | `validate_tooth_frame_object` |  |
| 492 | `validate_scene_uniqueness` | Reject duplicate canonical asset IDs even if Blender auto-added .001 names. |
| 514 | `migrate_scene_assets` | Idempotent additive migration for saved DSG 9.x scenes. |
| 543 | `family_snapshot` | CQS query: immutable-ish JSON-safe view of one loaded dental family. |

## [dental_assets.py](../dental_assets.py)

569 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 31 | class `DentalAssetContractError` | Raised when a dental asset or contract violates the shared schema. |
| 35 | `_contract_path` |  |
| 40 | `_load_contract` |  |
| 52 | `contract` | Return a defensive copy of the canonical contract. |
| 57 | `contract_path` |  |
| 61 | `contract_version` |  |
| 66 | `contract_sha256` |  |
| 70 | `schema` |  |
| 74 | `property_keys` |  |
| 78 | `role_names` |  |
| 82 | `coordinate_spaces` |  |
| 86 | `source_names` |  |
| 90 | `coordinate_frame` | Return the definitive DSG_TOOTH_LOCAL_V1 frame descriptor. |
| 95 | `mesh_attribute_names` |  |
| 99 | `derived_geometry_names` |  |
| 103 | `mapping_quality_states` |  |
| 107 | `mapping_metadata_schema` |  |
| 111 | `accepted_previous_hashes` |  |
| 116 | `verify_contract_sidecar` | Fail-fast verification for packaged JSON/sha256 copies. |
| 128 | `valid_fdi` |  |
| 141 | `normalize_fdi` |  |
| 152 | `arch_from_fdi` |  |
| 164 | `side_from_fdi` |  |
| 176 | `neighbor_fdis` | Return nominal mesial/distal family neighbors from FDI identity only. |
| 193 | `tooth_class_from_fdi` |  |
| 200 | `family_id` |  |
| 205 | `_normalize_role` |  |
| 214 | `normalize_landmark_name` | Normalize a canonical landmark name. |
| 227 | `normalize_import_landmark_name` |  |
| 234 | `asset_id` |  |
| 249 | `object_prefix` |  |
| 258 | `object_name` |  |
| 273 | `required_landmarks` | Required canonical landmark names for one tooth family. |
| 296 | `optional_landmarks` |  |
| 304 | `all_landmarks` |  |
| 310 | `library_filename` |  |
| 314 | `library_path` |  |
| 318 | `library_family_collection_name` |  |
| 323 | `initial_prosthetic_fdis` |  |
| 328 | `deferred_prosthetic_fdis` |  |
| 333 | `family_descriptor` |  |
| 361 | `validate_mapping_metadata` | Validate optional recognition/mapping metadata without creating v2. |
| 426 | `canonical_recognition_payload` | Build a strict payload accepted by DSG from an external recognition engine. |
| 481 | `validate_recognition_payload` |  |
| 519 | `_validate_contract` |  |
| 567 | `assert_contract_integrity` |  |

## [dental_mapping/__init__.py](../dental_mapping/__init__.py)

19 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [dental_mapping/anatomic_fit.py](../dental_mapping/anatomic_fit.py)

197 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 23 | class `AnatomicFitPolicy` |  |
| 32 | `_matrix` |  |
| 36 | `_frame_relative_to_crown` |  |
| 45 | `_bounds_in_frame` |  |
| 57 | `dimensions_in_frame` |  |
| 63 | `_ratio` |  |
| 77 | `_smoothstep01` |  |
| 82 | `_warp_axis` | Symmetric side-aware displacement: zero near center, full at envelope. |
| 97 | `warp_frame_point` |  |
| 107 | `warp_crown_local_point` | Apply exactly the stored CrownTarget deformation to a semantic reference point. |
| 126 | `create_crown_target` |  |

## [dental_mapping/derived_geometry.py](../dental_mapping/derived_geometry.py)

159 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | `_items` |  |
| 33 | `_normalized` |  |
| 39 | `derive_tooth_frame_matrix` |  |
| 86 | `materialize_tooth_frame` |  |
| 110 | `_project_local` |  |
| 118 | `derive_geometry` | Compute compact loops/envelopes as data, not duplicate SSOT objects. |
| 158 | `store_derived_geometry` |  |

## [dental_mapping/emergence.py](../dental_mapping/emergence.py)

224 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | `_matrix` |  |
| 24 | `_replace_object` |  |
| 37 | `_create_empty` |  |
| 52 | `_create_mesh_asset` |  |
| 74 | `_warp_world` |  |
| 79 | `_warped_axis_matrix` | Warp origin + basis probes, prioritizing authored Z as prosthetic axis. |
| 115 | `_snap_mesh_asset_to_crown` |  |
| 143 | `derive_emergence_assets` |  |
| 219 | `get_emergence_region` |  |
| 223 | `get_prosthetic_axis` |  |

## [dental_mapping/eoff.py](../dental_mapping/eoff.py)

33 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `import_eoff` |  |

## [dental_mapping/eoff_core.py](../dental_mapping/eoff_core.py)

89 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `_clean_lines` |  |
| 17 | `parse_eoff` |  |

## [dental_mapping/landmark_refine.py](../dental_mapping/landmark_refine.py)

73 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 19 | `_bvh` |  |
| 28 | `refine_landmarks` |  |

## [dental_mapping/landmark_transfer.py](../dental_mapping/landmark_transfer.py)

41 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `_matrix` |  |
| 18 | `transfer_landmarks` | Project canonical library landmarks through the registered ghost transform. |

## [dental_mapping/library.py](../dental_mapping/library.py)

305 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | class `ReferenceObjectSnapshot` |  |
| 33 | class `FamilyReferenceSnapshot` |  |
| 40 | `library_path` |  |
| 44 | `library_available` |  |
| 48 | `require_library` |  |
| 58 | `ensure_runtime_collection` |  |
| 68 | `_library_catalog` |  |
| 74 | `validate_library_catalog` | Cheap structural validation without appending the whole .blend. |
| 113 | `_append_objects` | Append exact object datablocks and return the resulting references. |
| 130 | `_remove_temporary_objects` |  |
| 143 | `_matrix_tuple` |  |
| 147 | `_mesh_snapshot` |  |
| 158 | `read_family_reference_snapshot` | Read library semantics without leaving landmark/frame assets in the scene. |
| 243 | `load_role_template` | Idempotently append one persistent library template by FDI/role. |
| 273 | `load_tooth_template` |  |
| 277 | `load_crown_template` |  |
| 282 | `read_crown_gold_standard` | Read approved Gold Standard JSON from the canonical CROWN_TEMPLATE without scene pollution. |

## [dental_mapping/mesh_distance_core.py](../dental_mapping/mesh_distance_core.py)

187 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | class `MeshDistanceResult` |  |
| 32 | `_v3` |  |
| 39 | `closest_point_on_triangle` | Ericson closest-point-on-triangle, returning point and squared distance. |
| 78 | `closest_points_segments` | Return closest points and squared distance between two finite 3D segments. |
| 103 | `_segment_triangle_hit` | Möller-Trumbore segment/triangle intersection. |
| 120 | `triangle_triangle_distance` | Exact Euclidean distance between two 3D triangles, with witness points. |
| 144 | `_aabb_distance2` |  |
| 149 | `exact_mesh_surface_distance` | Compute exact triangle-surface distance using an AABB-safe broad phase. |

## [dental_mapping/migration.py](../dental_mapping/migration.py)

90 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | `_landmarks_for_fdi` |  |
| 40 | `rebuild_legacy_tooth_frame` |  |
| 70 | `migrate_scene_compatibility` |  |

## [dental_mapping/occlusal_fit.py](../dental_mapping/occlusal_fit.py)

170 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 21 | class `OcclusalFitPolicy` |  |
| 26 | `_mesh_topology` |  |
| 48 | `_functional_landmark_objects` |  |
| 59 | `_reproject_landmarks` |  |
| 87 | `fit_occlusion` |  |

## [dental_mapping/proximal_fit.py](../dental_mapping/proximal_fit.py)

176 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 14 | class `ProximalFitPolicy` |  |
| 23 | `_tree` |  |
| 32 | `_region_points` |  |
| 58 | `measure_side` |  |
| 114 | `_score` |  |
| 130 | `fit_translation` | Search one symmetric MD translation; never deform one proximal face alone. |

## [dental_mapping/registration.py](../dental_mapping/registration.py)

452 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | class `RegistrationPolicy` |  |
| 33 | `_np` |  |
| 38 | `_matrix_tuple` |  |
| 42 | `_world_points` |  |
| 58 | `_pca` |  |
| 74 | `_proper_signed_permutations` |  |
| 89 | `_bvh_for_object` |  |
| 97 | `_nearest_rms` |  |
| 114 | `_coarse_transform` |  |
| 147 | `_rigid_kabsch` |  |
| 170 | `_icp_refine` |  |
| 211 | `_mapping_state` |  |
| 224 | `create_ghost` |  |
| 263 | `register_template_to_patient` | Coarse PCA registration followed by trimmed surface ICP. |
| 325 | `_stamp_crown_ghost` |  |
| 363 | `create_crown_ghost` |  |
| 399 | `register_crown_template_to_patient` | Gold Standard coronal registration: CROWN_TEMPLATE -> CROWN_GHOST -> TOOTH. |

## [dental_mapping/scoring.py](../dental_mapping/scoring.py)

47 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `crown_candidate_score` | Return an explainable score; hard invalid states are never compensated. |

## [dental_mapping/service.py](../dental_mapping/service.py)

573 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 31 | `get_dental_asset_contract` |  |
| 42 | `family_descriptor` |  |
| 46 | `required_landmarks` |  |
| 50 | `load_tooth_template` |  |
| 54 | `load_crown_template` |  |
| 58 | `_patient_tooth` |  |
| 68 | `_remove_ghost` |  |
| 77 | `map_patient_crown` | Canonical Gold Standard crown mapping pipeline: CROWN_TEMPLATE -> CROWN_GHOST -> TOOTH. |
| 202 | `map_patient_tooth` | Backward-compatible alias. In 9.1.1 coronal semantics use CROWN_GHOST. |
| 208 | `get_landmarks` |  |
| 236 | `get_tooth_frame` |  |
| 241 | `get_mapping_quality` |  |
| 257 | `select_crown_candidate` | Current library contains one canonical CrownTemplate per FDI family. |
| 271 | `_frame_blend` |  |
| 281 | `_landmark_position` |  |
| 287 | `_target_frame_for_missing_site` |  |
| 311 | `fit_crown_to_neighbors` |  |
| 386 | `fit_crown_to_neighbors.target_point` |  |
| 439 | `fit_occlusion` |  |
| 450 | `get_emergence_region` |  |
| 454 | `get_prosthetic_axis` |  |
| 458 | `_matrix_json` |  |
| 464 | `build_implant_planning_context` | JSON-safe dental/prosthetic context. Surgical anatomy is supplied elsewhere. |
| 501 | `get_gold_standard` |  |
| 505 | `analyze_implant_bone_support` |  |
| 521 | `analyze_implant_neighbor_clearance` |  |
| 528 | `analyze_interdental_space` |  |
| 533 | `analyze_implant_diameter_options` |  |
| 540 | `build_full_implant_context` |  |
| 546 | `prepare_implant_axis_from_prosthetic_context` |  |
| 551 | `evaluate_implant_candidate` |  |
| 558 | `apply_implant_bone_support_heatmap` |  |
| 571 | `clear_implant_bone_support_heatmap` |  |

## [dental_mapping/surgical_context.py](../dental_mapping/surgical_context.py)

1074 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 27 | `_modules` |  |
| 32 | `_resolve_implant` |  |
| 54 | `_patient_tooth` |  |
| 62 | `_tooth_frame` |  |
| 66 | `_implant_geometry` |  |
| 76 | `_orthogonal_basis` |  |
| 88 | `_stats` |  |
| 101 | `analyze_implant_bone_support` | Sample the already-loaded CBCT around the implant surface. |
| 222 | `_heatmap_rgba` | Auditable cold→hot ramp: blue→cyan→green→yellow→red. |
| 232 | `_surface_normal_probe_points` | Return flattened surface-normal probe positions and vertex count. |
| 262 | `_axis_radial_probe_points` |  |
| 276 | `_sample_heatmap_values` | Visualization sampler only; scoring remains axial×angular elsewhere. |
| 315 | `apply_implant_bone_support_heatmap` | Visualize existing DSG CBCT support values on the implant. |
| 426 | `clear_implant_bone_support_heatmap` |  |
| 449 | `_world_bvh_and_vertices` |  |
| 464 | `_world_triangles` | Return evaluated world-space triangles as an ``(N,3,3)`` NumPy array. |
| 494 | `_sample_vectors` |  |
| 501 | `_object_surface_distance` | World-space mesh separation with intersection detection. |
| 557 | `_object_surface_distance_full_vertex` | Bidirectional full-vertex BVH recheck used as an upper bound for exact mode. |
| 567 | `_object_surface_distance_exact` | Triangle-surface confirmation verifier.  Fails closed if broad phase is incomplete. |
| 613 | `analyze_implant_neighbor_clearance` |  |
| 676 | `analyze_interdental_space` | Context metric between the two segmented teeth adjacent to a missing site. |
| 714 | `_virtual_implant_world_geometry` | Evaluated implant geometry with local radial XY scaled to a trial diameter. |
| 745 | `_world_geometry_to_object_surface_distance` | Distance from virtual triangulated geometry to a real Blender mesh. |
| 831 | `analyze_implant_diameter_options` | Evaluate real catalog diameters on the current implant trajectory. |
| 916 | `enrich_implant_context` |  |
| 952 | `prepare_implant_axis_from_prosthetic_context` | Prepare DSG's existing one-shot implant axis from final prosthetic assets. |
| 1018 | `evaluate_implant_candidate` | Return objective candidate metrics; apply only explicitly supplied constraints. |

## [dental_mapping/validation.py](../dental_mapping/validation.py)

106 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 14 | class `MappingQuality` |  |
| 22 | `MappingQuality.as_dict` |  |
| 26 | `_landmark_map` |  |
| 36 | `quality_from_mapping` |  |
| 71 | `validate_frame_semantics` | Check semantic ordering in DSG_TOOTH_LOCAL_V1 without silently flipping axes. |

## [dental_surface_geometry.py](../dental_surface_geometry.py)

663 líneas · imports Blender: mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 33 | `valid_mesh` |  |
| 43 | `fdi_arch` |  |
| 55 | `fdi_position` |  |
| 62 | `tooth_class` |  |
| 73 | `_world_vertex_arrays` |  |
| 94 | `_world_face_arrays` |  |
| 120 | `_face_adjacency` |  |
| 137 | `_connected_components` |  |
| 155 | `_normalise` |  |
| 163 | `_tooth_centroid` |  |
| 168 | `_single_tooth_axis` | Estimate an unsigned root-crown axis from one segmented tooth. |
| 185 | `_arch_plane_axis` |  |
| 211 | `_end_score` | How likely is the +axis extreme to be the IOS-visible crown end? |
| 250 | `estimate_occlusal_axis` | Return a root->crown unit axis plus diagnostics for one dental arch. |
| 296 | `occlusal_incisal_patch` | Extract a connected IOS-visible occlusal/incisal face patch. |
| 407 | `registration_crown_patch` | Return a root-safe coronal crown shell for automatic IOS registration. |
| 492 | `build_registration_crown_graph_data` | Return the connected coronal crown shells used by Plan A alignment. |
| 560 | `build_occlusal_graph_data` | Return points/normals/edges for occlusal+incisal CBCT patches only. |
| 622 | `build_occlusal_reference_bvh` | BVH of only the occlusal/incisal surfaces of *reference_objects*. |

## [dicom_module.py](../dicom_module.py)

24 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [dicom_probe.py](../dicom_probe.py)

29 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | `validate` |  |

## [dsg_logging.py](../dsg_logging.py)

115 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 34 | `_privacy_redact` |  |
| 44 | class `_PrivacyFormatter` |  |
| 45 | `_PrivacyFormatter.format` |  |
| 50 | `default_log_dir` |  |
| 64 | `_level_from_env` |  |
| 69 | `configure` | Attach DSG handlers once. Returns the log file path (None if unwritable). |
| 95 | `unconfigure` |  |
| 106 | `set_level` |  |
| 111 | `log_file` |  |

## [engine_preflight.py](../engine_preflight.py)

85 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 13 | `validate` |  |
| 69 | `main` |  |

## [error_handling.py](../error_handling.py)

140 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 21 | class `MessageSpec` |  |
| 62 | `spec` |  |
| 66 | `redact` | Best-effort privacy redaction for technical logs. |
| 84 | `user_message` |  |
| 93 | `log_exception` |  |
| 100 | `log_fallback` |  |
| 115 | `report` | Report a stable user message through a Blender operator when available. |
| 129 | `error_payload` |  |

## [evidence_context.py](../evidence_context.py)

222 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | `repository` |  |
| 29 | `repository_summary` |  |
| 33 | `get_evidence_rule` |  |
| 37 | `get_evidence_topic` |  |
| 41 | `search_offline_evidence` |  |
| 45 | `_store` |  |
| 49 | `_load` |  |
| 60 | `build_evidence_update_request` |  |
| 67 | `get_evidence_update_request` |  |
| 71 | `store_evidence_update_proposal` |  |
| 82 | `get_evidence_update_proposal` |  |
| 86 | `evidence_status` |  |
| 102 | class `DSGEvidenceProperties` |  |
| 108 | class `DSG_OT_EvidenceCopySummary` | `dsg.evidence_copy_summary` · Copiar resumen científico |
| 111 | `DSG_OT_EvidenceCopySummary.execute` |  |
| 117 | class `DSG_OT_EvidenceCopyRule` | `dsg.evidence_copy_rule` · Copiar regla + bibliografía |
| 120 | `DSG_OT_EvidenceCopyRule.execute` |  |
| 130 | class `DSG_OT_EvidenceCopySearch` | `dsg.evidence_copy_search` · Buscar offline y copiar |
| 133 | `DSG_OT_EvidenceCopySearch.execute` |  |
| 143 | class `DSG_OT_EvidenceCopyUpdateRequest` | `dsg.evidence_copy_update_request` · Preparar actualización MCP |
| 146 | `DSG_OT_EvidenceCopyUpdateRequest.execute` |  |
| 161 | class `DSG_PT_EvidenceRepository` | `DSG_PT_evidence_repository` · Evidencia científica · Offline |
| 169 | `DSG_PT_EvidenceRepository.draw` |  |
| 207 | `register` |  |
| 215 | `unregister` |  |

## [evidence_core.py](../evidence_core.py)

314 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 23 | class `EvidenceRepositoryError` |  |
| 27 | `_base_dir` |  |
| 33 | `_json` |  |
| 44 | `_sha256` |  |
| 52 | `load_repository` |  |
| 92 | `_validate_repository_links` |  |
| 105 | `_indexes` |  |
| 112 | `repository_summary` |  |
| 132 | `_text_blob` |  |
| 145 | `query_references` |  |
| 162 | `query_rules` |  |
| 177 | `get_rule` |  |
| 190 | `get_topic_context` |  |
| 214 | `search_offline_evidence` |  |
| 237 | `_normalize_topics` |  |
| 243 | `build_update_request` | Build a live-search task for MCP without modifying active evidence. |
| 278 | `validate_update_proposal` |  |
| 305 | `due_for_review` |  |

## [failtests.py](../failtests.py)

63 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 13 | class `FailtestResult` |  |
| 19 | `_ok` |  |
| 23 | `run_all` |  |

## [frame_boolean_path_core.py](../frame_boolean_path_core.py)

158 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | class `BooleanPathStation` |  |
| 38 | class `BooleanPathProfile` |  |
| 53 | `_validate_centerline` |  |
| 64 | `_at_distance` |  |
| 72 | `profile_boolean_path` | Profile a retained-material centerline against a Boolean-cut mesh. |

## [frame_boolean_section_core.py](../frame_boolean_section_core.py)

296 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | class `InvalidBooleanSection` | Slice cannot be proven to be a closed section of the requested solid. |
| 22 | class `BooleanSection` |  |
| 40 | `_point_in_polygon` |  |
| 57 | `_moments_uv` | Positive signed area, first and second area moments around UV origin. |
| 77 | `_closed_manifold` |  |
| 89 | `measure_boolean_section` | Compute the local actual mesh section containing an interior probe point. |
| 159 | `measure_boolean_section.identify` |  |
| 207 | `measure_boolean_section.root_of` |  |
| 230 | `measure_boolean_section.relative_depth` |  |
| 266 | class `SectionReferenceComparison` | Geometry ratio only. This cannot validate stiffness or device strength. |
| 277 | `compare_section_to_nominal_circle` | Compare real section area/weak-axis bending to an *ideal* circular bar. |

## [frame_contact_core.py](../frame_contact_core.py)

200 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 16 | class `NoFeasibleContact` | No depth satisfies the supplied contact and remaining-section limits. |
| 21 | class `ContactPolicy` |  |
| 30 | class `ContactSection` |  |
| 45 | class `ContactRouteEstimate` |  |
| 56 | `_finite_positive` |  |
| 63 | `_valid_policy` |  |
| 90 | `circular_section_after_planar_cut` | Closed-form cross-section for 0 <= penetration <= radius. |
| 133 | `select_contact_section` | Choose shallowest depth meeting *explicit*, caller-supplied geometry limits. |
| 158 | `estimate_contact_route` | Return estimated shifted centreline and section/contact integrals. |
| 189 | `estimate_contact_route.integrate` |  |

## [frame_fem_core.py](../frame_fem_core.py)

848 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 42 | class `StructuralSolveError` |  |
| 47 | class `Node` |  |
| 52 | `Node.__post_init__` |  |
| 58 | class `BeamElement` |  |
| 82 | `BeamElement.area` |  |
| 86 | `BeamElement.I` |  |
| 90 | `BeamElement.J` |  |
| 94 | `BeamElement.working_stress_mpa` |  |
| 102 | class `LoadCase` |  |
| 107 | `LoadCase.__post_init__` |  |
| 113 | class `OptimizationConfig` |  |
| 146 | class `SolveBundle` |  |
| 156 | class `OptimizationResult` |  |
| 165 | `_local_stiffness` |  |
| 200 | `_transformation` |  |
| 235 | `_dof` |  |
| 239 | `_active_element_indices` |  |
| 243 | `assemble_stiffness` | Assemble K; SciPy sparse when available, NumPy dense otherwise. |
| 276 | `_build_load_vector` |  |
| 289 | `_element_result` |  |
| 356 | `solve_load_cases` |  |
| 449 | `assemble_and_solve` |  |
| 454 | `build_ground_structure` |  |
| 478 | `_system_metrics` |  |
| 522 | `_resize_elements` |  |
| 544 | `_candidate_prune_indices` |  |
| 556 | `_try_prune_candidates` |  |
| 577 | `_fallback_perpendicular` |  |
| 588 | `_reinforcement_direction` |  |
| 604 | `_node_too_close` |  |
| 612 | `_clone_beam_for_growth` |  |
| 617 | `add_local_triangle_reinforcements` |  |
| 671 | `optimize_reinforcement` |  |
| 754 | `make_sleeve_load_cases` |  |
| 765 | `make_sleeve_load_cases.unit` |  |

## [frame_geodesic_fem.py](../frame_geodesic_fem.py)

74 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 16 | class `InvalidBeamPath` |  |
| 20 | `append_geodesic_beams` | Represent every bend in a curved reinforcement with beam segments. |

## [frame_geodesic_groups.py](../frame_geodesic_groups.py)

219 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 19 | class `GroupPruningResult` |  |
| 31 | class `InvalidGeodesicGroups` |  |
| 35 | `_compact` |  |
| 77 | `_evaluate` |  |
| 119 | `prune_geodesic_groups` | Greedily minimize balanced volume + compliance, subject to hard limits. |
| 155 | `prune_geodesic_groups.fixed_frame_member` |  |
| 167 | `prune_geodesic_groups.evaluate` |  |
| 178 | `prune_geodesic_groups.objective` |  |

## [frame_geodesic_paths.py](../frame_geodesic_paths.py)

207 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 19 | class `NoValidSurfaceRoute` | No permitted intrinsic route connects the requested endpoints. |
| 24 | class `GeodesicSurfacePath` |  |
| 32 | `route_surface_vertices` | Find an intrinsic mesh-edge route under hard restrictions. |
| 102 | `_validate_face_anchor` | Validate an exact projected face anchor; never snap across a nearby sheet. |
| 132 | `route_surface_face_anchors` | Route exact triangle anchors without leaving the surface or using 3D shortcuts. |

## [frame_perimeter_fem.py](../frame_perimeter_fem.py)

92 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 18 | class `InvalidPerimeterLoop` |  |
| 23 | class `PerimeterLoop` |  |
| 32 | `append_perimeter_loop` | Append four surface-routed members as one atomic perimeter addition. |

## [frame_sleeve_junction_core.py](../frame_sleeve_junction_core.py)

154 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 21 | class `InvalidSleeveJunction` |  |
| 26 | class `SleeveJunctionPreflight` |  |
| 39 | `_finite_vector` |  |
| 46 | `_line_prefix` | Return exact arclength-truncated prefix, interpolating the tube radius. |
| 71 | `preflight_sleeve_junction` | Allow only the target sleeve's *outer wall junction* as provisional. |

## [frame_structural.py](../frame_structural.py)

1916 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 42 | `_json_points` |  |
| 61 | `_frame_obj` |  |
| 70 | `_passive_obj` |  |
| 77 | `_support_nodes` |  |
| 92 | `persist_support_nodes` | Persist explicit P1..P4 semantics without changing frame geometry. |
| 108 | `_sleeve_context` |  |
| 133 | `_nearest_sleeve_attachment` |  |
| 160 | `_segment_intersects_sleeve_lumen` | Conservative sampled test against the finite cylindrical lumen keep-out. |
| 178 | `_polyline_midpoint` |  |
| 183 | `_sample_local_thickness` | Reuse DSG's own BVH/raycast wall-thickness probe on the current frame mesh. |
| 213 | `_route_between` |  |
| 229 | `get_frame_context` |  |
| 254 | `analyze_frame_structure` |  |
| 328 | `propose_frame_reinforcements` | Propose topology only; does not modify geometry or apply booleans. |
| 403 | `get_contract` |  |
| 422 | `_fem_vec` |  |
| 426 | `_fem_safe_unit` |  |
| 436 | `_fem_profile_config` |  |
| 466 | `_fem_material_element` |  |
| 479 | `_fem_sleeve_cardinal_points` |  |
| 495 | `_fem_build_keep_out` |  |
| 504 | `_fem_build_keep_out.check` |  |
| 539 | `_fem_build_model` |  |
| 657 | `_fem_build_geodesic_model` | Read-only experimental FEM model with true surface-following beam chains. |
| 859 | `analyze_geodesic_frame_fem` | Compare stiffness/volume of curved routes without replacing clinical guides. |
| 885 | `estimate_geodesic_frame_contact` | Read-only local planar contact estimate using the actual optimized FEM radii. |
| 975 | `analyze_geodesic_group_topology` | Balanced, read-only group pruning after the nominal curved-beam FEM run. |
| 1021 | `_fem_summary` |  |
| 1065 | `analyze_frame_fem` | Run FEM without touching Blender geometry. |
| 1078 | `_remove_existing_fem_reinforcements` |  |
| 1090 | `_validate_fem_candidate_sweep` | Hard preBoolean sweep before replacing any previously confirmed curves. |
| 1204 | `create_fem_reinforcements` | Stage a complete FEM candidate before replacing previously confirmed geometry. |
| 1380 | class `DSG_OT_OptimizeFrameFEM` | `dsg.optimize_frame_fem` · Optimize Frame |
| 1386 | `DSG_OT_OptimizeFrameFEM.execute` |  |
| 1412 | `preview_geodesic_fem_paths` | Create nonexported Blender previews from exactly the curved FEM chains. |
| 1504 | class `DSG_OT_PreviewGeodesicFrameFEM` | `dsg.preview_geodesic_frame_fem` · Preview Surface-Geodesic Reinforcements (Experimental) |
| 1510 | `DSG_OT_PreviewGeodesicFrameFEM.execute` |  |
| 1531 | class `DSG_OT_EstimateGeodesicContact` | `dsg.estimate_geodesic_contact` · Evaluate Contact Profile (Experimental) |
| 1557 | `DSG_OT_EstimateGeodesicContact.invoke` |  |
| 1560 | `DSG_OT_EstimateGeodesicContact.draw` |  |
| 1567 | `DSG_OT_EstimateGeodesicContact.execute` |  |
| 1591 | class `DSG_OT_AnalyzeGeodesicGroups` | `dsg.analyze_geodesic_groups` · Optimize Geodesic Groups (Experimental, Read-only) |
| 1600 | `DSG_OT_AnalyzeGeodesicGroups.execute` |  |
| 1620 | `inspect_final_boolean_guide_section` | Measure one requested section of the *actual* final Boolean guide. |
| 1677 | `inspect_final_boolean_guide_path` | Sample true mesh sections along an explicitly INSIDE-the-solid path. |
| 1729 | class `DSG_OT_InspectFinalBooleanPath` | `dsg.inspect_final_boolean_path` · Profile Sections Along Final Guide (Experimental) |
| 1747 | `DSG_OT_InspectFinalBooleanPath.invoke` |  |
| 1750 | `DSG_OT_InspectFinalBooleanPath.draw` |  |
| 1759 | `DSG_OT_InspectFinalBooleanPath.execute` |  |
| 1805 | class `DSG_OT_InspectFinalBooleanSection` | `dsg.inspect_final_boolean_section` · Inspect Final Guide Section (Experimental) |
| 1826 | `DSG_OT_InspectFinalBooleanSection.invoke` |  |
| 1829 | `DSG_OT_InspectFinalBooleanSection.draw` |  |
| 1837 | `DSG_OT_InspectFinalBooleanSection.execute` |  |
| 1863 | class `DSG_OT_AnalyzeGeodesicFrameFEM` | `dsg.analyze_geodesic_frame_fem` · Analyze Surface-Geodesic FEM (Experimental) |
| 1872 | `DSG_OT_AnalyzeGeodesicFrameFEM.execute` |  |
| 1899 | `register` |  |
| 1911 | `unregister` |  |

## [frame_structural_core.py](../frame_structural_core.py)

144 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 18 | `_p3` |  |
| 24 | `distance` |  |
| 29 | `polyline_length` |  |
| 34 | `point_at_fraction` |  |
| 55 | `structural_need_proxy` | Return an uncalibrated geometric ranking proxy, never a pass/fail rule. |
| 82 | `normalize_scores` |  |
| 93 | `single_sleeve_primary_topology` | Canonical topology invariant requested by the DSG architect. |
| 122 | `validate_thresholds` | Apply only explicit user/MCP thresholds; never invent engineering limits. |

## [frame_surface_corridor.py](../frame_surface_corridor.py)

379 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 36 | class `CorridorRoute` |  |
| 45 | `_graph_from_csr` |  |
| 57 | `multisource_intrinsic_distance` | Distance to the nearest seed on the mesh-edge graph. |
| 116 | `curvature_proxy` | Dimensionless local normal variation, vectorized over directed edges. |
| 140 | `weighted_route` | Minimum weighted graph route with face-anchor endpoint candidates. |
| 277 | `resample_polyline` |  |
| 304 | `try_potpourri_heat_distance` | Optional robust intrinsic heat distance. Returns (dist, solver, backend, error). |
| 328 | `try_potpourri_edgeflip` | Optional continuous path straightening via geometry-central edge flips. |

## [frame_swept_clearance_core.py](../frame_swept_clearance_core.py)

162 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | class `InvalidClearanceGeometry` |  |
| 22 | class `SphereKeepOut` |  |
| 29 | class `CylinderKeepOut` |  |
| 38 | class `SweptClearanceReport` |  |
| 49 | `_validated_zone` |  |
| 71 | `_signed_distance` |  |
| 84 | `check_swept_tube_clearance` | Certify clearance ONLY for the supplied explicit zones. |

## [glyph_library.py](../glyph_library.py)

289 líneas · imports Blender: bmesh, bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 83 | `_base_cells` |  |
| 93 | `_accent_cells` |  |
| 113 | `normalize_character` | Return a supported uppercase glyph key without external font fallback. |
| 129 | `glyph_cells` |  |
| 154 | `prepare_text` | Normalize a clinical identifier and report substitutions. |
| 167 | `_collect_text_cells` |  |
| 186 | `create_glyph_mesh_object` | Create a low-poly, internally generated engraving mesh. |
| 220 | `create_glyph_mesh_object.vertex_at` |  |
| 288 | `supported_characters` |  |

## [guide_assets.py](../guide_assets.py)

45 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 18 | class `GuideAssetError` |  |
| 23 | `_manifest` |  |
| 32 | `load_text` |  |

## [guide_export/__init__.py](../guide_export/__init__.py)

15 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [guide_export/blender_adapter.py](../guide_export/blender_adapter.py)

199 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 29 | `mesh_arrays` | Evaluated (modifiers applied) world-space triangles, as exported to STL. |
| 49 | `bvh_from_arrays` |  |
| 53 | class `BVHRayCaster` | ``RayCaster`` implementation backed by ``mathutils.bvhtree``. |
| 56 | `BVHRayCaster.__init__` |  |
| 59 | `BVHRayCaster.cast` |  |
| 73 | `object_clearance_mm` | Minimum distance between two meshes. |
| 109 | `fingerprint` | SHA-256 of a file, or of a directory's files (sorted, content-hashed). |
| 138 | `_vec` |  |
| 145 | `_safe` |  |
| 153 | `read_export_context` | Collect case/plan metadata. ``guide_ns`` is the ``guide_module`` |
| 193 | `find_mandibular_canal` |  |

## [guide_export/mesh_checks.py](../guide_export/mesh_checks.py)

275 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 18 | class `CheckResult` | Outcome of one quality check. |
| 31 | `CheckResult.as_dict` |  |
| 36 | class `RayCaster` | Abstraction over a ray/mesh intersection engine (BVH in Blender). |
| 39 | `RayCaster.cast` | Return ``(distances, hit_normals)``; ``distances`` is ``inf`` on miss. |
| 46 | `_as_mesh` |  |
| 54 | `triangle_normals_and_areas` |  |
| 63 | `manifold_report` | Every undirected edge must be shared by exactly two triangles, and the |
| 95 | `signed_volume_mm3` |  |
| 104 | `connected_components` | Vertex component labels via vectorised label propagation + pointer jumping. |
| 129 | class `Island` |  |
| 135 | `islands` | Connected shells sorted largest first (by face count, then area). |
| 153 | `island_removal_decision` | Decide whether dropping every island except the largest is safe to do |
| 176 | `_sample_faces` |  |
| 185 | `wall_thickness_report` | Shoot a ray from each sampled face centroid along its inward normal; |
| 228 | class `NumpyRayCaster` | Brute-force Möller–Trumbore ray caster. O(rays × triangles): use only |
| 232 | `NumpyRayCaster.__init__` |  |
| 237 | `NumpyRayCaster.cast` |  |
| 265 | `clearance_status` |  |

## [guide_export/policy.py](../guide_export/policy.py)

43 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | class `ExportPolicy` | Thresholds used by the export quality gate. |
| 37 | `ExportPolicy.__post_init__` |  |

## [guide_export/report.py](../guide_export/report.py)

93 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 24 | `sha256_file` |  |
| 32 | `report_path_for` |  |
| 38 | class `ImplantRecord` |  |
| 50 | class `ExportContext` | Everything the report needs, gathered by the Blender adapter. |
| 64 | `build_report` |  |
| 87 | `write_report` | Atomically write the JSON sidecar next to ``stl_path``. |

## [guide_export/service.py](../guide_export/service.py)

136 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 27 | class `ExportOptions` | User decisions taken in the export dialog. |
| 37 | class `GateResult` |  |
| 41 | `GateResult.blocking` |  |
| 45 | `GateResult.warnings` |  |
| 48 | `GateResult.extend` |  |
| 52 | `_default_arrays` |  |
| 57 | `_default_caster` |  |
| 62 | `_default_clearance` |  |
| 67 | class `ExportGate` | Runs the checks in the order the operator needs them. |
| 70 | `ExportGate.__init__` |  |
| 81 | `ExportGate.check_islands` |  |
| 90 | `ExportGate.check_solid` |  |
| 111 | `ExportGate.check_anatomy` |  |
| 129 | `summarize` | One-line human summary for ``Operator.report``. |

## [guide_module.py](../guide_module.py)

25 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [icon_manager.py](../icon_manager.py)

92 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | `_relative_luma` |  |
| 28 | `_theme_variant` | Return ``light`` or ``dark`` without mutating user preferences. |
| 45 | `register` |  |
| 70 | `unregister` |  |
| 81 | `icon_id` |  |

## [implant_catalogues.py](../implant_catalogues.py)

99 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 29 | `_load` |  |
| 32 | `_nominal` | key -> (file data, catalogue entry) for every reference-based library. |
| 42 | `_libraries` |  |
| 56 | `signature_paths` |  |
| 59 | `rows` |  |
| 82 | `nominal_body_mesh` | Circumscribed nominal body cylinder, without an invented thread or collar. |
| 95 | `inside_envelope` | True when a local mesh (platform at +length/2, axis +Z) fits the nominal envelope. |

## [implant_optimization.py](../implant_optimization.py)

204 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | `_matrix` |  |
| 18 | `_frame` |  |
| 21 | `pose_matrix` | Rotate about ``pivot`` in the implant frame, then translate in that frame. |
| 33 | `movement` | Size of a proposal: lateral + axial in mm, tilt weighted 1 mm per 10°. |
| 38 | `_evaluate` |  |
| 46 | `rejection_rank` | Display ordering only; never changes admissibility or clinical limits. |
| 55 | `rejected_options` |  |
| 61 | `search_position` | Bounded local search. |
| 74 | `search_position.run` |  |
| 81 | `search_position.best_score` |  |
| 109 | `_asset_matches` |  |
| 115 | `search_size` | Compare catalogue sizes with the platform and axis fixed. |
| 152 | `search_size.rank` |  |
| 154 | `search_size.rank` |  |
| 165 | `_over_cap` |  |
| 169 | `search_joint_sizes` | Finite size/translation stencil. Axis fixed; coronal depth never increased. |
| 174 | `search_joint_sizes.collect` |  |
| 193 | `search_joint_sizes.rank` |  |

## [implant_optimizer_worker.py](../implant_optimizer_worker.py)

97 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 4 | `run` |  |
| 9 | `run.progress` |  |
| 16 | `run.mesh` |  |
| 35 | `run.measured` |  |
| 88 | `main` |  |

## [installation_lock.py](../installation_lock.py)

41 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 7 | `installation_lock` |  |
| 36 | `installation_running` |  |

## [lifecycle.py](../lifecycle.py)

140 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 22 | `activate` | Start a fresh add-on lifecycle generation. |
| 31 | `deactivate` | Stop callbacks first, before modules remove RNA classes/properties. |
| 39 | `is_active` |  |
| 45 | `current_epoch` |  |
| 49 | `_forget_wrapper` |  |
| 61 | `register_timer` | Register a timer that automatically dies after add-on reload/unregister. |
| 68 | `register_timer.guarded_callback` |  |
| 101 | `unregister_timer` |  |
| 111 | `cancel_module_timers` |  |
| 125 | `cancel_all_timers` |  |
| 136 | `cancel_named_timers` | Cancel stage callbacks already completed synchronously by history. |

## [minidicom.py](../minidicom.py)

312 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 23 | class `InvalidDicomError` |  |
| 27 | class `_Errors` |  |
| 69 | `_clean_text` |  |
| 73 | `_decode` |  |
| 105 | `_skip_undefined` | Skip undefined-length item/sequence by scanning delimiter tags. |
| 129 | `_read_element` |  |
| 165 | class `Dataset` |  |
| 166 | `Dataset.__init__` |  |
| 174 | `Dataset.pixel_array` |  |
| 177 | `Dataset.__str__` |  |
| 182 | `dcmread` |  |
| 265 | `pixel_array` |  |
| 307 | class `_Pixels` |  |
| 309 | `_Pixels.pixel_array` |  |

## [optimizer_profile.py](../optimizer_profile.py)

19 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 6 | `settings` |  |
| 14 | `margins` |  |

## [organic_teeth.py](../organic_teeth.py)

277 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 33 | `model_grid` | Model grid size and native->model index ratio per axis (corner aligned). |
| 42 | `block_agreement` | Fraction of native neighbours inside one model cell that share a label. |
| 62 | `_bbox` |  |
| 68 | `_antialias` |  |
| 74 | `_components` |  |
| 82 | `_compact` |  |
| 87 | `_signed_volume` |  |
| 93 | `_closed` |  |
| 99 | `_model_region` | Model-grid labels for cells [start, stop); cells outside the grid are background. |
| 113 | class `NeighbourCache` | Anti-aliased level set of each tooth, computed once per batch. |
| 120 | `NeighbourCache.__init__` |  |
| 124 | `NeighbourCache._field` |  |
| 135 | `NeighbourCache.sample` |  |
| 145 | `organic_tooth` | Return (xyz vertices, faces, stats) for one tooth label. |
| 223 | `organic_tooth.field` |  |

## [pipeline_core/__init__.py](../pipeline_core/__init__.py)

3 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [pipeline_core/contracts.py](../pipeline_core/contracts.py)

101 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | class `DSGError` |  |
| 6 | `DSGError.__init__` |  |
| 10 | class `ContractError` |  |
| 11 | class `InputError` |  |
| 12 | class `EngineError` |  |
| 13 | class `MeshingError` |  |
| 18 | `_geometry` |  |
| 26 | class `VolumeInput` |  |
| 34 | `VolumeInput.parse` |  |
| 45 | `compat_to_fdi` |  |
| 53 | class `Labelmap` |  |
| 61 | `Labelmap.parse` |  |
| 73 | `Labelmap.summary` |  |
| 79 | class `ResultManifest` |  |
| 82 | `ResultManifest.parse` |  |

## [pipeline_core/trace.py](../pipeline_core/trace.py)

32 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 5 | class `RunTrace` | Exportable record: no request paths, patient names, raw IDs or logs. |
| 7 | `RunTrace.__init__` |  |
| 13 | `RunTrace.write` |  |
| 18 | `RunTrace._close` |  |
| 21 | `RunTrace.start` |  |
| 25 | `RunTrace.fallback` |  |
| 27 | `RunTrace.fail` |  |
| 31 | `RunTrace.finish` |  |

## [roadmap_module.py](../roadmap_module.py)

1685 líneas · imports Blender: bpy, mathutils

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 79 | `_now` |  |
| 83 | `_case_fingerprint` | Session-bound non-PHI fingerprint for the loaded CBCT. |
| 97 | `_case_fingerprint._uid_digest` |  |
| 114 | `_valid_fdi` |  |
| 118 | `_safe_float` |  |
| 128 | `_clean_points` |  |
| 153 | `canonical_implant_plan` | Create the only accepted dsg.roadmap.v1 implant-roadmap shape. |
| 269 | `_load_store` |  |
| 280 | `_save_store` |  |
| 284 | `_save_plan` |  |
| 296 | `_get_plan` |  |
| 300 | `_append_log` |  |
| 311 | `_step` |  |
| 318 | `_tooth_objects` | Single source of truth: the current CBCT dentition builder owns tooth instances. |
| 323 | `_tooth_analysis_completed` |  |
| 331 | `_find_tooth_object` |  |
| 350 | `_find_implant_for_fdi` |  |
| 360 | `_json_vec` |  |
| 377 | `_axis_from_tooth_mesh` | Fallback PCA for reopened/pre-8.4 objects that lack persisted axis data. |
| 429 | `_tooth_axis_data` |  |
| 442 | class `DSG_OT_SetAxisFromFDI` | `dsg.set_axis_from_fdi` · Propose Implant Axis from FDI |
| 449 | `DSG_OT_SetAxisFromFDI.execute` |  |
| 522 | `get_case_state` |  |
| 581 | `_mark_external_completion` |  |
| 589 | `reconcile_plan` | Update plan status from scene truth without fabricating completed work. |
| 768 | `_view3d_override` | Return a valid VIEW_3D override for timer/MCP initiated operators. |
| 794 | `_call_operator` |  |
| 806 | `_audit_parameters_for_step` |  |
| 823 | `execute_step` |  |
| 948 | class `_BridgeEnvelope` |  |
| 960 | class `_ThreadingLocalServer` |  |
| 965 | class `_BridgeHandler` |  |
| 966 | `_BridgeHandler.handle` |  |
| 983 | `_dispatch_operation` |  |
| 1396 | `_dispatch_main` |  |
| 1415 | `_bridge_timer` |  |
| 1436 | `start_bridge` |  |
| 1480 | `stop_bridge` |  |
| 1515 | class `DSGRoadmapProperties` |  |
| 1522 | class `DSG_OT_StartMCPBridge` | `dsg.start_mcp_bridge` · Start MCP Bridge |
| 1526 | `DSG_OT_StartMCPBridge.execute` |  |
| 1532 | class `DSG_OT_StopMCPBridge` | `dsg.stop_mcp_bridge` · Stop MCP Bridge |
| 1536 | `DSG_OT_StopMCPBridge.execute` |  |
| 1542 | class `DSG_OT_CopyMCPBridgeConfig` | `dsg.copy_mcp_bridge_config` · Copy MCP Bridge Config |
| 1546 | `DSG_OT_CopyMCPBridgeConfig.execute` |  |
| 1559 | class `DSG_OT_RefreshRoadmapStatus` | `dsg.refresh_roadmap_status` · Refresh Roadmap |
| 1563 | `DSG_OT_RefreshRoadmapStatus.execute` |  |
| 1572 | class `DSG_PT_MCPRoadmap` | `DSG_PT_MCPRoadmap` · MCP · Roadmap clínico |
| 1590 | `DSG_PT_MCPRoadmap.poll` |  |
| 1593 | `DSG_PT_MCPRoadmap.draw` |  |
| 1668 | `register` |  |
| 1674 | `unregister` |  |

## [runtime_bootstrap.py](../runtime_bootstrap.py)

227 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 19 | `_tag_all_view3d_redraw` |  |
| 30 | `_install_ui_timer` |  |
| 43 | `_ensure_install_ui_timer` |  |
| 54 | `_selected_engine` |  |
| 62 | `component_status` |  |
| 94 | `ui_component_status` |  |
| 95 | `invalidate_ui_component_status` |  |
| 96 | `ui_engines_ready` |  |
| 97 | `verification_state` |  |
| 98 | `remote_install_state` |  |
| 99 | `state` |  |
| 100 | `all_required_ready` |  |
| 103 | `_verify` |  |
| 114 | `start_background_verification` |  |
| 123 | `ensure_first_run_install_started` |  |
| 127 | `reset_auto_start_for_retry` |  |
| 131 | `start_install_all` |  |
| 135 | class `DSG_OT_InstallSegmentationEngines910` |  |
| 153 | `DSG_OT_InstallSegmentationEngines910.execute` |  |
| 176 | class `DSG_OT_RuntimePreflight` | `dsg.runtime_preflight` ·  |
| 181 | `DSG_OT_RuntimePreflight.execute` |  |
| 193 | class `DSG_OT_RunSafetyFailtests` | `dsg.run_safety_failtests` · Ejecutar failtests DSG |
| 199 | `DSG_OT_RunSafetyFailtests.execute` |  |
| 217 | `register` |  |
| 222 | `unregister` |  |

## [section_geometry.py](../section_geometry.py)

39 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 8 | `raster_sections` |  |

## [section_optimizer.py](../section_optimizer.py)

218 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 12 | class `SectionField` |  |
| 13 | `SectionField.__init__` |  |
| 33 | `SectionField.__init__.raster` |  |
| 73 | `SectionField.maps` |  |
| 82 | `SectionField.maps.fraction` |  |
| 89 | `SectionField.assess` |  |
| 132 | `SectionField.export` |  |
| 136 | `SectionField.assess_matrix` |  |
| 143 | `exact_section_evaluation` |  |
| 171 | `search_sections` |  |
| 195 | `search_sections.rank` |  |

## [segmentation_engines.py](../segmentation_engines.py)

545 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 57 | class `EngineStatus` |  |
| 71 | `EngineStatus.public` |  |
| 75 | `_require_blender_52` |  |
| 88 | `_scripts_root` |  |
| 99 | `addon_dir` |  |
| 103 | `runtime_root` |  |
| 113 | `site_packages` |  |
| 119 | `repos_root` |  |
| 125 | `models_root` |  |
| 131 | `totalseg_home` |  |
| 137 | `totalseg_results` |  |
| 143 | `toothseg_results` |  |
| 149 | `umamba2_models` |  |
| 155 | `active_site_paths` |  |
| 169 | `environment_for_engine` |  |
| 207 | `_contains_checkpoint` |  |
| 232 | `_totalseg_status` |  |
| 251 | `_toothseg_status` |  |
| 274 | `find_umamba2_model_dir` |  |
| 288 | `_umamba2_status` |  |
| 318 | `verify_engine` |  |
| 338 | `verify_all` |  |
| 342 | `invalidate_cache` |  |
| 346 | `engine_supports` |  |
| 350 | `_nvidia_driver_present` |  |
| 361 | `runtime_compute_status` | Use numerical proof for the current wheel; ignore stale receipts. |
| 373 | `refresh_runtime_compute_status` |  |
| 384 | `_python_path` |  |
| 414 | `_blender_binary_path` |  |
| 426 | `_status_file` |  |
| 430 | `_request_file` |  |
| 434 | `_install_log` |  |
| 438 | `_write_state` |  |
| 449 | `install_state` |  |
| 470 | `start_install` |  |
| 533 | `quick_status` |  |
| 537 | `diagnostics` |  |

## [segmentation_install_worker.py](../segmentation_install_worker.py)

404 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 20 | `_status_path` |  |
| 24 | `_write` |  |
| 44 | `_run` |  |
| 49 | `_python` |  |
| 56 | `_env` |  |
| 67 | `_pip` |  |
| 82 | `prepare_compute` |  |
| 85 | `prepare_compute.check` |  |
| 110 | `prepare_dicom` |  |
| 126 | `_download` |  |
| 168 | `_github_snapshot` |  |
| 187 | `_find_dataset` |  |
| 192 | `_has_checkpoint` |  |
| 207 | `_verify_runtime` | A folder's presence is insufficient: load each official model on CPU. |
| 228 | `install_totalseg` |  |
| 259 | `install_toothseg` |  |
| 300 | `install_umamba2` |  |
| 344 | `main` |  |
| 351 | `_install_request` |  |

## [source_parts.py](../source_parts.py)

31 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | `exec_source_parts` |  |

## [surface_nets_geometry.py](../surface_nets_geometry.py)

92 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 9 | `image` |  |
| 14 | `surface_nets` |  |
| 25 | `arrays` |  |
| 29 | `poly` |  |
| 33 | `split_manual` |  |
| 39 | `split_atlas` |  |
| 51 | `volume` |  |
| 54 | `topology` |  |
| 60 | `boundary_samples` |  |
| 66 | `consistency` |  |
| 74 | `geometry` |  |
| 78 | `roughness_radius` |  |
| 90 | `sampled_distance` |  |

## [surface_smoothing.py](../surface_smoothing.py)

243 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 16 | `_signed_volume` |  |
| 22 | `_cap` |  |
| 27 | `_compensate_volume` |  |
| 42 | `_compensate_volume.candidate` |  |
| 71 | `smooth_surface_preserving_volume` | Return same-index positions and measured guards; never modify inputs. |
| 186 | `_display_nodes` |  |
| 204 | `set_measured_display_smoothing` | Cache offsets once; display them with a reversible same-topology modifier. |

## [tools/check_quality.py](../tools/check_quality.py)

15 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [tools/gen_index.py](../tools/gen_index.py)

128 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 17 | `cell` |  |
| 21 | `attribute` |  |
| 35 | `symbols` |  |
| 50 | `generate` |  |
| 106 | `main` |  |

## [tools/metrics.py](../tools/metrics.py)

53 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 6 | `silent` |  |
| 14 | `scan` |  |
| 30 | `compare` |  |
| 31 | `main` |  |

## [tooth_analysis.py](../tooth_analysis.py)

1364 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 62 | `universal_arch_counterpart` |  |
| 74 | `_expected_arch_from_universal` |  |
| 81 | class `ToothRecord` | One explicit semantic tooth label from an AI engine. |
| 105 | `ToothRecord.public_dict` |  |
| 109 | `valid_fdi` |  |
| 115 | `_valid_fdi` |  |
| 119 | `universal_to_fdi` | Deterministic mapping from an explicit Universal label to FDI. |
| 137 | `fdi_to_universal` |  |
| 151 | `arch_from_fdi` |  |
| 155 | `side_from_fdi` |  |
| 159 | `tooth_class_from_fdi` |  |
| 166 | `_spacing` |  |
| 173 | `_pca_axis_from_component` | Physical PCA for an already-labelled tooth component. |
| 197 | `pca_axis_from_xyz` |  |
| 237 | `orient_axis_apical` | Orient a tooth PCA line using only explicit FDI arch semantics. |
| 258 | `_semantic_label_patient_centroids` | Return physical DICOM-LPS centroids for semantic labels. |
| 295 | `correct_universal_arch_array` | Validate maxilla/mandible identity without rewriting teeth. |
| 406 | `correct_universal_semantics_array` | Run arch validation first, then DICOM-LPS laterality correction. |
| 418 | `correct_universal_mirroring_array` | Correct tooth laterality at voxel level, never by whole-label merge. |
| 507 | `analyze_tooth_mask_components` | Connected-component analysis for one learned tooth label. |
| 552 | `validate_universal_labelmap_topology` | Return learned tooth labels that contain >1 anatomically significant island. |
| 590 | `validate_semantic_records` | Structural/laterality/sequence gate without inventing missing teeth. |
| 625 | `mcp_payload` |  |
| 641 | `reconcile_universal_dentition_paths` | Repair normalized tooth instances by following each tooth through a |
| 690 | `reconcile_universal_dentition_paths._labels_for_arch` |  |
| 696 | `reconcile_universal_dentition_paths._clip_box` |  |
| 703 | `reconcile_universal_dentition_paths._component_data` |  |
| 732 | `reconcile_universal_dentition_paths._seed_core_data` | Return eroded interior cores for one learned tooth label. |
| 790 | `reconcile_universal_dentition_paths._competitive_seed_guard` | Prevent one reconstructed tooth from swallowing a neighbouring tooth. |
| 862 | `reconcile_universal_dentition_paths._sample_coords` |  |
| 869 | `reconcile_universal_dentition_paths._corridor_metrics` |  |
| 884 | `reconcile_universal_dentition_paths._corridor_metrics._measure` |  |
| 919 | `reconcile_universal_dentition_paths._process_arch` |  |
| 1064 | `reconcile_universal_dentition_paths._process_arch._sequence_for_label` |  |
| 1076 | `reconcile_universal_dentition_paths._process_arch._midpoint_window_seed` | Carve a local identity core around the expected neighbour midpoint. |
| 1197 | `reconcile_universal_dentition_paths._process_arch._seed_connected_raw` | Non-destructive fallback for one normalized tooth identity. |

## [ui_style.py](../ui_style.py)

248 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 64 | `_priority_marker` | Add a small original blue swatch without mutating the user's Blender theme. |
| 77 | class `_PrimaryActionProxy` | Make the single clinical next-step visibly turquoise in native Blender. |
| 86 | `_PrimaryActionProxy.__init__` |  |
| 89 | `_PrimaryActionProxy.__getattr__` |  |
| 92 | `_PrimaryActionProxy.__setattr__` |  |
| 95 | `_PrimaryActionProxy.operator` |  |
| 100 | `primary_action` | Required next step: large turquoise action, visually a clear "next". |
| 109 | `secondary_action` | Optional/corrective action: muted slate-blue, subordinate to primary. |
| 118 | `secondary_action_alt` | Second nested route level: medium clinical blue. |
| 127 | `secondary_action_soft` | Third nested route level: soft sky blue. |
| 136 | `tertiary_action` | Review/navigation/accessory action: compact blue-gray. |
| 145 | `compact_action` | Very low-priority inline tool, using the tertiary blue-gray tone. |
| 154 | `destructive_action` | Discard/reset action. Keep it tertiary in hierarchy; confirmation owns risk. |
| 163 | `header_row` |  |
| 169 | `apply_dsg_theme` | Restore the restrained 8.0 turquoise selected-state and roundness. |
| 216 | `restore_dsg_theme` | Restore every Blender theme value captured by :func:`apply_dsg_theme`. |
| 235 | `_redraw_all` |  |

## [version.py](../version.py)

3 líneas · imports Blender: ninguno directo

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|

## [workflow_history.py](../workflow_history.py)

258 líneas · imports Blender: bpy

| Línea | Símbolo | Descripción / bl_idname |
|---:|---|---|
| 32 | `begin` | No checkpoint: native undo records the step when the operator ends. |
| 37 | `commit` | Finish delayed guide presentation so the undo step is complete. |
| 51 | `has_checkpoint` | There are no archived checkpoints; the legacy undo repairs always run. |
| 56 | `automation_suspended` |  |
| 60 | `restore_runtime` |  |
| 64 | `undo_previous` |  |
| 72 | `_before_undo` |  |
| 109 | `_after_undo` |  |
| 116 | `_after_load` |  |
| 121 | `_cancel_modal` |  |
| 142 | `self_module` |  |
| 147 | `_track_modal` |  |
| 156 | `_wrap_execute` |  |
| 158 | `_wrap_execute.wrapped` |  |
| 166 | `_wrap_invoke` |  |
| 168 | `_wrap_invoke.wrapped` |  |
| 176 | `_wrap_modal` |  |
| 178 | `_wrap_modal.wrapped` |  |
| 213 | `prepare_operators` |  |
| 246 | `register` |  |
| 253 | `unregister` |  |

## Operadores, paneles y menús por bl_idname

| bl_idname | Etiqueta | Clase | Archivo | Línea |
|---|---|---|---|---:|
| `DICOMWIZARDPRO_PT_import` | DICOM | `DICOMWIZARDPRO_PT_import` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 169 |
| `DICOMWIZARDPRO_PT_main` | DICOM | `DICOMWIZARDPRO_PT_main` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 99 |
| `DICOMWIZARDPRO_PT_mpr_review` | DICOM | `DICOMWIZARDPRO_PT_mpr_review` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 444 |
| `DICOMWIZARDPRO_PT_result` | DICOM | `DICOMWIZARDPRO_PT_result` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 521 |
| `DICOMWIZARDPRO_PT_segment` | DICOM | `DICOMWIZARDPRO_PT_segment` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 255 |
| `DICOMWIZARDPRO_PT_segment_advanced` | Advanced / Avanzado | `DICOMWIZARDPRO_PT_segment_advanced` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 429 |
| `DICOMWIZARDPRO_PT_view` | DICOM | `DICOMWIZARDPRO_PT_view` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 218 |
| `DICOMWIZARDPRO_PT_view_advanced` | Advanced / Avanzado | `DICOMWIZARDPRO_PT_view_advanced` | [_dicom_parts/07_panels_registration.py](../_dicom_parts/07_panels_registration.py) | 238 |
| `DICP_PT_main` | Alignment | `DICP_PT_Main` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 1205 |
| `DSG_PT_MCPRoadmap` | MCP · Roadmap clínico | `DSG_PT_MCPRoadmap` | [roadmap_module.py](../roadmap_module.py) | 1572 |
| `DSG_PT_clinical_context` | Paciente · Contexto clínico MCP | `DSG_PT_ClinicalContext` | [clinical_context.py](../clinical_context.py) | 434 |
| `DSG_PT_evidence_repository` | Evidencia científica · Offline | `DSG_PT_EvidenceRepository` | [evidence_context.py](../evidence_context.py) | 161 |
| `DSG_PT_main` | DSG | `DSG_PT_Main` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 3276 |
| `DSG_SUITE_PT_main` | DSG | `DSG_SUITE_PT_Main` | [core.py](../core.py) | 3805 |
| `DSG_SUITE_PT_workflow_controls` | Control del flujo | `DSG_SUITE_PT_WorkflowControls` | [core.py](../core.py) | 3661 |
| `dct.apply_cut` | Apply Final Boolean | `DCT_OT_ApplyCut` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1403 |
| `dct.clear_cut_selection` | Clear Selection | `DCT_OT_ClearCutSelection` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1696 |
| `dct.select_being_cut` | Select Object Being Cut | `DCT_OT_SelectBeingCut` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1364 |
| `dct.select_making_cut` | Select Object Making Cut | `DCT_OT_SelectMakingCut` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1379 |
| `dct.voxel_remesh` | Apply Voxel Remesh | `DCT_OT_VoxelRemesh` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1342 |
| `dicom_wizard_pro.adjust_tissue_sensitivity` | Ajustar segmentación | `DICOMWIZARDPRO_OT_adjust_tissue_sensitivity` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 746 |
| `dicom_wizard_pro.align_mpr_from_active_plane` | Alinear los 3 cortes desde este plano | `DICOMWIZARDPRO_OT_align_mpr_from_active_plane` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 569 |
| `dicom_wizard_pro.analyze_tissues` | Analizar densidades | `DICOMWIZARDPRO_OT_analyze_tissues` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 728 |
| `dicom_wizard_pro.auto_threshold` | Automático | `DICOMWIZARDPRO_OT_auto_threshold` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 506 |
| `dicom_wizard_pro.back_to_segmentation` | Volver a segmentación | `DICOMWIZARDPRO_OT_back_to_segmentation` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2327 |
| `dicom_wizard_pro.back_to_viewer` | Volver a visualización | `DICOMWIZARDPRO_OT_back_to_viewer` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 685 |
| `dicom_wizard_pro.calculate_segmentation` | Segmentar automáticamente | `DICOMWIZARDPRO_OT_calculate_segmentation` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 814 |
| `dicom_wizard_pro.center_plane` | Centrar plano | `DICOMWIZARDPRO_OT_center_plane` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 676 |
| `dicom_wizard_pro.clear_drawings` | Borrar máscara | `DICOMWIZARDPRO_OT_clear_drawings` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 714 |
| `dicom_wizard_pro.close_gaps` | Cerrar discontinuidades | `DICOMWIZARDPRO_OT_close_gaps` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 883 |
| `dicom_wizard_pro.close_safe_mpr` | Salir de revisión | `DICOMWIZARDPRO_OT_close_safe_mpr` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 515 |
| `dicom_wizard_pro.continue_with_dicom_stl` | Continuar con STL DICOM | `DICOMWIZARDPRO_OT_continue_with_dicom_stl` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2015 |
| `dicom_wizard_pro.direct_dicom_to_surface` | Segmentar DICOM | `DICOMWIZARDPRO_OT_direct_dicom_to_surface` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 1804 |
| `dicom_wizard_pro.export_surface_stl` | Exportar STL | `DICOMWIZARDPRO_OT_export_surface_stl` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2216 |
| `dicom_wizard_pro.fill_holes` | Rellenar huecos internos | `DICOMWIZARDPRO_OT_fill_holes` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 897 |
| `dicom_wizard_pro.fit_clinical_preview` | Centrar CBCT | `DICOMWIZARDPRO_OT_fit_clinical_preview` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 565 |
| `dicom_wizard_pro.fit_view` | Centrar vista | `DICOMWIZARDPRO_OT_fit_view` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 554 |
| `dicom_wizard_pro.generate_surface` | Generar superficie | `DICOMWIZARDPRO_OT_generate_surface` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2283 |
| `dicom_wizard_pro.keep_largest_island` | Conservar isla mayor | `DICOMWIZARDPRO_OT_keep_largest_island` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 869 |
| `dicom_wizard_pro.move_review_plane` | Mover plano | `DICOMWIZARDPRO_OT_move_review_plane` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 177 |
| `dicom_wizard_pro.new_file` | Back to DICOM Start | `DICOMWIZARDPRO_OT_new_file` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 463 |
| `dicom_wizard_pro.next` | Siguiente | `DICOMWIZARDPRO_OT_next` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 265 |
| `dicom_wizard_pro.prepare_ai_alignment` | Crear referencia dental CBCT y continuar | `DICOMWIZARDPRO_OT_prepare_ai_alignment` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2057 |
| `dicom_wizard_pro.prepare_alignment` | Continue to Alignment | `DICOMWIZARDPRO_OT_prepare_alignment` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2105 |
| `dicom_wizard_pro.radiographic_quad_view` | Revisión 3D con planos | `DICOMWIZARDPRO_OT_radiographic_quad_view` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 143 |
| `dicom_wizard_pro.refresh` | Actualizar | `DICOMWIZARDPRO_OT_refresh` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 576 |
| `dicom_wizard_pro.remove_small_islands` | Eliminar islas pequeñas | `DICOMWIZARDPRO_OT_remove_small_islands` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 855 |
| `dicom_wizard_pro.reset_mpr_orientation` | Restablecer orientación MPR | `DICOMWIZARDPRO_OT_reset_mpr_orientation` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 631 |
| `dicom_wizard_pro.reset_plane` | Enderezar | `DICOMWIZARDPRO_OT_reset_plane` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 538 |
| `dicom_wizard_pro.reset_tissue_range` | Restaurar umbrales automáticos | `DICOMWIZARDPRO_OT_reset_tissue_range` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 795 |
| `dicom_wizard_pro.rotate_review_plane` | Rotar plano | `DICOMWIZARDPRO_OT_rotate_review_plane` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 318 |
| `dicom_wizard_pro.segment_all` | Segmentar todo | `DICOMWIZARDPRO_OT_segment_all` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 1777 |
| `dicom_wizard_pro.segment_semantic_structure` | Segmentar estructura | `DICOMWIZARDPRO_OT_segment_semantic_structure` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 1745 |
| `dicom_wizard_pro.select_file` | Elegir DICOM / DCM | `DICOMWIZARDPRO_OT_select_file` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 198 |
| `dicom_wizard_pro.select_surface` | Seleccionar superficie | `DICOMWIZARDPRO_OT_select_surface` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 2310 |
| `dicom_wizard_pro.select_target` | Seleccionar control | `DICOMWIZARDPRO_OT_select_target` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 705 |
| `dicom_wizard_pro.to_segmentation` | Siguiente: segmentar | `DICOMWIZARDPRO_OT_to_segmentation` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 595 |
| `dicom_wizard_pro.undo_last` | Deshacer última acción | `DICOMWIZARDPRO_OT_undo_last` | [_dicom_parts/06_operators_b.py](../_dicom_parts/06_operators_b.py) | 661 |
| `dicp.auto_detect` | Detect models | `DICP_OT_AutoDetect` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 249 |
| `dicp.back_to_alignment` | Deshacer última acción | `DICP_OT_BackToAlignment` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 1020 |
| `dicp.clear_landmarks` | Redibujar puntos | `DICP_OT_ClearLandmarks` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 999 |
| `dicp.import_ios_stl` | Import intraoral STL | `DICP_OT_ImportIOSSTL` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 179 |
| `dicp.pick_landmarks` | Marcar zonas | `DICP_OT_PickLandmarks` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 305 |
| `dicp.reset` | Back to Alignment Start | `DICP_OT_Reset` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 1050 |
| `dicp.restore_source` | Restaurar posición | `DICP_OT_RestoreSource` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 966 |
| `dicp.review_alignment` | Revisar | `DICP_OT_ReviewAlignment` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 896 |
| `dicp.run_alignment` | Alinear modelos | `DICP_OT_RunAlignment` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 764 |
| `dicp.send_to_dsg` | Siguiente | `DICP_OT_SendToDSG` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 915 |
| `dicp.use_selection` | Usar 2 seleccionados | `DICP_OT_UseSelection` | [_alignment_parts/01_alignment_operators_ui.py](../_alignment_parts/01_alignment_operators_ui.py) | 276 |
| `dsg.accept_closed_ios_model` | Use Closed IOS Model and Continue | `DSG_OT_AcceptClosedIOSModel` | [_guide_parts/02_implant_animation_geometry_c.py](../_guide_parts/02_implant_animation_geometry_c.py) | 167 |
| `dsg.add_drill_channel` | Create Drill Channels | `DSG_OT_AddDrillChannel` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3305 |
| `dsg.add_sleeve` | Sleeve Preview | `DSG_OT_AddSleeve` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2603 |
| `dsg.ai_status_refresh` | Revisar motores de segmentación | `DSG_OT_AIStatusRefresh` | [cbct_dental_module.py](../cbct_dental_module.py) | 2673 |
| `dsg.all_protected_neighbors` | MOSTRAR TODOS LOS VECINOS | `DSG_OT_ResetProtectedNeighbors` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 195 |
| `dsg.analyze_geodesic_frame_fem` | Analyze Surface-Geodesic FEM (Experimental) | `DSG_OT_AnalyzeGeodesicFrameFEM` | [frame_structural.py](../frame_structural.py) | 1863 |
| `dsg.analyze_geodesic_groups` | Optimize Geodesic Groups (Experimental, Read-only) | `DSG_OT_AnalyzeGeodesicGroups` | [frame_structural.py](../frame_structural.py) | 1591 |
| `dsg.analyze_implant_safety` | Analyze Implant Safety | `DSG_OT_AnalyzeImplantSafety` | [_guide_parts/03_blockout_frame_geometry_b.py](../_guide_parts/03_blockout_frame_geometry_b.py) | 167 |
| `dsg.analyze_retention` | Analyze Coronary Perimeter | `DSG_OT_AnalyzeRetention` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3413 |
| `dsg.apply_implant_optimization` | ACEPTAR CAMBIOS | `DSG_OT_ApplyOptimization` | [blender/implant_optimizer.py](../blender/implant_optimizer.py) | 444 |
| `dsg.apply_microscrews_to_frame` | Add Microscrews to Frame | `DSG_OT_ApplyMicroscrewsToFrame` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1886 |
| `dsg.apply_patient_engrave` | Engrave Name on Guide | `DSG_OT_ApplyPatientEngrave` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 91 |
| `dsg.apply_post_irrigation_lateral_opening` | Apply Post-Irrigation Lateral Opening | `DSG_OT_ApplyPostIrrigationLateralOpening` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2919 |
| `dsg.apply_reinforcements` | Add Connectors and Continue | `DSG_OT_ApplyReinforcements` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2600 |
| `dsg.apply_selected_blockout_relief` | Apply Selected Local Relief | `DSG_OT_ApplySelectedBlockoutRelief` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3463 |
| `dsg.apply_sleeves` | Apply Sleeves | `DSG_OT_ApplySleeves` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3052 |
| `dsg.assign_upper_cavity` | ASIGNAR MALLA DE CAVIDAD | `DSG_OT_AssignUpperCavity` | [blender/upper_cavity_safety.py](../blender/upper_cavity_safety.py) | 249 |
| `dsg.auto_prepare_retention` | Prepare Model | `DSG_OT_AutoPrepareRetention` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3506 |
| `dsg.build_tube_frame` | Generate Tubular Frame | `DSG_OT_BuildTubeFrame` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1 |
| `dsg.cancel_irrigation_preview` | Discard Preview | `DSG_OT_CancelIrrigationPreview` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 1184 |
| `dsg.cancel_microscrew_preview` | Discard Pending Microscrew | `DSG_OT_CancelMicroscrewPreview` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1827 |
| `dsg.cancel_reinforcement_preview` | Discard Pending Connector | `DSG_OT_CancelReinforcementPreview` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2529 |
| `dsg.capture_axis` | Capture Axis from View | `DSG_OT_CaptureAxis` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2946 |
| `dsg.capture_lateral_opening_view` | Use Current View for Post-Irrigation Opening | `DSG_OT_CaptureLateralOpeningView` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2301 |
| `dsg.cbct_accept_fdi` | Confirmar FDI | `DSG_OT_CBCTAcceptFDI` | [cbct_dental_module.py](../cbct_dental_module.py) | 2194 |
| `dsg.cbct_cancel_post_smooth` | Cancelar suavizado | `DSG_OT_CancelPostSmooth` | [cbct_post_smoothing.py](../cbct_post_smoothing.py) | 253 |
| `dsg.cbct_delete_tooth` | Marcar diente como ausente | `DSG_OT_CBCTDeleteTooth` | [cbct_dental_module.py](../cbct_dental_module.py) | 2556 |
| `dsg.cbct_edit_fdi` | Corregir FDI seleccionado | `DSG_OT_CBCTEditFDI` | [cbct_dental_module.py](../cbct_dental_module.py) | 2415 |
| `dsg.cbct_improve_geometry` | Mejorar geometría | `DSG_OT_CBCTImproveGeometry` | [cbct_dental_module.py](../cbct_dental_module.py) | 2306 |
| `dsg.cbct_post_smooth_report` | Resultado del suavizado | `DSG_OT_PostSmoothReport` | [cbct_post_smoothing.py](../cbct_post_smoothing.py) | 258 |
| `dsg.cbct_post_smooth_teeth` | Suavizar dientes | `DSG_OT_PostSmoothTeeth` | [cbct_post_smoothing.py](../cbct_post_smoothing.py) | 239 |
| `dsg.cbct_swap_arches` | Intercambiar maxilar / mandíbula | `DSG_OT_CBCTSwapArches` | [cbct_dental_module.py](../cbct_dental_module.py) | 2479 |
| `dsg.cbct_toggle_fdi` | Mostrar/Ocultar FDI | `DSG_OT_CBCTToggleFDI` | [cbct_dental_module.py](../cbct_dental_module.py) | 2403 |
| `dsg.cbct_toggle_surface_smoothing` | Suavizar superficie CBCT | `DSG_OT_CBCTToggleSurfaceSmoothing` | [cbct_dental_module.py](../cbct_dental_module.py) | 1043 |
| `dsg.center_selected_microscrew_mpr` | Center Microscrew MPR | `DSG_OT_CenterSelectedMicroscrewMPR` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 261 |
| `dsg.clean_guide_islands` | Remove Separate Fragments | `DSG_OT_CleanGuideIslands` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 176 |
| `dsg.clear_base_perimeter` | Clear Base Perimeter | `DSG_OT_ClearBasePerimeter` | [_guide_parts/02_implant_animation_geometry_b.py](../_guide_parts/02_implant_animation_geometry_b.py) | 1897 |
| `dsg.clear_contour` | Clear Outline | `DSG_OT_ClearContour` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3842 |
| `dsg.clear_dicom_measurements` | Clear DICOM Measurements | `DSG_OT_ClearDICOMMeasurements` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 1562 |
| `dsg.clear_engrave_preview` | Clear Preview | `DSG_OT_ClearEngravePreview` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 74 |
| `dsg.clear_irrigation_flow_simulation` | Clear Irrigation Simulation | `DSG_OT_ClearIrrigationFlowSimulation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 2292 |
| `dsg.clear_protected_neighbors` | QUITAR DIENTES VECINOS | `DSG_OT_ClearProtectedNeighbors` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 208 |
| `dsg.clinical_add_condition` | Añadir condición | `DSG_OT_ClinicalAddCondition` | [clinical_context.py](../clinical_context.py) | 346 |
| `dsg.clinical_add_lab` | Añadir analítica | `DSG_OT_ClinicalAddLab` | [clinical_context.py](../clinical_context.py) | 365 |
| `dsg.clinical_add_medication` | Añadir medicamento | `DSG_OT_ClinicalAddMedication` | [clinical_context.py](../clinical_context.py) | 299 |
| `dsg.clinical_clear` | Borrar contexto clínico | `DSG_OT_ClinicalClear` | [clinical_context.py](../clinical_context.py) | 423 |
| `dsg.clinical_confirm_review` | Confirmar revisión clínica | `DSG_OT_ClinicalConfirmReview` | [clinical_context.py](../clinical_context.py) | 406 |
| `dsg.clinical_copy_request` | Copiar petición clínica MCP | `DSG_OT_ClinicalCopyRequest` | [clinical_context.py](../clinical_context.py) | 389 |
| `dsg.clinical_remove_last_medication` | Quitar último medicamento | `DSG_OT_ClinicalRemoveLastMedication` | [clinical_context.py](../clinical_context.py) | 331 |
| `dsg.clinical_save_basics` | Guardar datos básicos | `DSG_OT_ClinicalSaveBasics` | [clinical_context.py](../clinical_context.py) | 279 |
| `dsg.close_dicom_review` | Close DICOM Review | `DSG_OT_CloseDICOMReview` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 421 |
| `dsg.close_model_base` | Close Model Base Automatically | `DSG_OT_CloseModelBase` | [_guide_parts/02_implant_animation_geometry_c.py](../_guide_parts/02_implant_animation_geometry_c.py) | 232 |
| `dsg.close_scan_holes` | Close Scan Holes | `DSG_OT_CloseScanHoles` | [_guide_parts/02_implant_animation_geometry_b.py](../_guide_parts/02_implant_animation_geometry_b.py) | 2510 |
| `dsg.color_implant_inclination_plane` | Color del marco | `DSG_OT_ColorInclinationPlane` | [blender/implant_plane.py](../blender/implant_plane.py) | 377 |
| `dsg.confirm_axis` | Confirm Axis | `DSG_OT_ConfirmAxis` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2997 |
| `dsg.confirm_blockout` | Confirm Blockout | `DSG_OT_ConfirmBlockout` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3518 |
| `dsg.confirm_contour` | Confirm Outline | `DSG_OT_ConfirmContour` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3856 |
| `dsg.confirm_drill` | Confirm Channels → Final Boolean | `DSG_OT_ConfirmDrill` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3648 |
| `dsg.confirm_implant` | Confirm Implants | `DSG_OT_ConfirmImplant` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4281 |
| `dsg.confirm_irrigation` | Apply Irrigation and Continue | `DSG_OT_ConfirmIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 2308 |
| `dsg.confirm_irrigation_preview` | Confirm | `DSG_OT_ConfirmIrrigationPreview` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 436 |
| `dsg.confirm_microscrew_preview` | Confirm Microscrew | `DSG_OT_ConfirmMicroscrewPreview` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1810 |
| `dsg.confirm_model` | Confirm Model | `DSG_OT_ConfirmModel` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2922 |
| `dsg.confirm_protected_neighbors` | CONFIRMAR SELECCIÓN | `DSG_OT_ConfirmProtectedNeighbors` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 220 |
| `dsg.confirm_reinforcement_preview` | Confirm Reinforcement Connector | `DSG_OT_ConfirmReinforcementPreview` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2492 |
| `dsg.confirm_sleeve` | Continue to Irrigation | `DSG_OT_ConfirmSleeve` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3239 |
| `dsg.confirm_tube_frame` | Confirm Frame | `DSG_OT_ConfirmTubeFrame` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2157 |
| `dsg.confirm_upper_cavities` | CONFIRMAR CAVIDADES SUPERIORES | `DSG_OT_ConfirmUpperCavities` | [blender/upper_cavity_safety.py](../blender/upper_cavity_safety.py) | 235 |
| `dsg.confirm_virtual_extraction` | SIGUIENTE | `DSG_OT_ConfirmVirtualExtraction` | [blender/virtual_extraction.py](../blender/virtual_extraction.py) | 222 |
| `dsg.continue_after_irrigation` | Continue After Irrigation | `DSG_OT_ContinueAfterIrrigation` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3022 |
| `dsg.continue_to_name_export` | Continue to Name and Export | `DSG_OT_ContinueToNameExport` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1670 |
| `dsg.copy_mcp_bridge_config` | Copy MCP Bridge Config | `DSG_OT_CopyMCPBridgeConfig` | [roadmap_module.py](../roadmap_module.py) | 1542 |
| `dsg.copy_pipeline_diagnostic` | Copiar diagnóstico | `DSG_OT_CopyPipelineDiagnostic` | [cbct_dental_module.py](../cbct_dental_module.py) | 2694 |
| `dsg.create_animated_drills` | Create Animated Drills | `DSG_OT_CreateAnimatedDrills` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1616 |
| `dsg.create_animated_microscrews` | Create Animated Screws | `DSG_OT_CreateAnimatedMicroscrews` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1968 |
| `dsg.create_apply_sleeves` | Create and Apply Sleeves | `DSG_OT_CreateApplySleeves` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2755 |
| `dsg.create_implant` | Create Implant | `DSG_OT_CreateImplant` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3892 |
| `dsg.create_implant_emergence_tubes` | Create Implant Emergence Tubes | `DSG_OT_CreateImplantEmergenceTubes` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4206 |
| `dsg.create_implant_inclination_plane` | Plano radiográfico del implante | `DSG_OT_CreateInclinationPlane` | [blender/implant_plane.py](../blender/implant_plane.py) | 340 |
| `dsg.create_sequential_insertion_animation` | Create Screw, Drill and Implant Sequence | `DSG_OT_CreateSequentialInsertionAnimation` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1957 |
| `dsg.discard_implant_optimization` | DESCARTAR CAMBIOS / CANCELAR | `DSG_OT_DiscardOptimization` | [blender/implant_optimizer.py](../blender/implant_optimizer.py) | 453 |
| `dsg.draw_base_perimeter` | Draw Base Perimeter | `DSG_OT_DrawBasePerimeter` | [_guide_parts/02_implant_animation_geometry_b.py](../_guide_parts/02_implant_animation_geometry_b.py) | 1819 |
| `dsg.edit_protected_neighbors` | ELEGIR DIENTES VECINOS | `DSG_OT_EditProtectedNeighbors` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 186 |
| `dsg.estimate_geodesic_contact` | Evaluate Contact Profile (Experimental) | `DSG_OT_EstimateGeodesicContact` | [frame_structural.py](../frame_structural.py) | 1531 |
| `dsg.evidence_copy_rule` | Copiar regla + bibliografía | `DSG_OT_EvidenceCopyRule` | [evidence_context.py](../evidence_context.py) | 117 |
| `dsg.evidence_copy_search` | Buscar offline y copiar | `DSG_OT_EvidenceCopySearch` | [evidence_context.py](../evidence_context.py) | 130 |
| `dsg.evidence_copy_summary` | Copiar resumen científico | `DSG_OT_EvidenceCopySummary` | [evidence_context.py](../evidence_context.py) | 108 |
| `dsg.evidence_copy_update_request` | Preparar actualización MCP | `DSG_OT_EvidenceCopyUpdateRequest` | [evidence_context.py](../evidence_context.py) | 143 |
| `dsg.export_guide_stl` | Export Guide STL | `DSG_OT_ExportGuideSTL` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 201 |
| `dsg.extraction_extension_preview` | VER EXTENSIÓN OCLUSAL | `DSG_OT_ExtensionPreview` | [blender/extraction_extension.py](../blender/extraction_extension.py) | 99 |
| `dsg.final_view_cbct_stl` | Toggle CBCT STL Layer | `DSG_OT_FinalViewCBCTSTL` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 571 |
| `dsg.final_view_model` | Toggle Model Layer | `DSG_OT_FinalViewModel` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 549 |
| `dsg.finish_segmented_teeth` | Mejorar dientes | `DSG_OT_FinishSegmentedTeeth` | [blender/segmentation_finish.py](../blender/segmentation_finish.py) | 158 |
| `dsg.force_confirm_blockout` | Continue After Manual Seating Review | `DSG_OT_ForceConfirmBlockout` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3665 |
| `dsg.force_orthographic_view` | Restore Orthographic Precision View | `DSG_OT_ForceOrthographicView` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2460 |
| `dsg.generate_blockout` | Generate Blockout | `DSG_OT_GenerateBlockout` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3346 |
| `dsg.inspect_final_boolean_path` | Profile Sections Along Final Guide (Experimental) | `DSG_OT_InspectFinalBooleanPath` | [frame_structural.py](../frame_structural.py) | 1729 |
| `dsg.inspect_final_boolean_section` | Inspect Final Guide Section (Experimental) | `DSG_OT_InspectFinalBooleanSection` | [frame_structural.py](../frame_structural.py) | 1805 |
| `dsg.install_ai_runtime` | Instalar motores de segmentación | `DSG_OT_InstallAIRuntime` | [cbct_dental_module.py](../cbct_dental_module.py) | 2654 |
| `dsg.install_dicom_runtime` | Preparar Motor DICOM offline | `DSG_OT_install_dicom_runtime` | [_dicom_parts/06_operators_a.py](../_dicom_parts/06_operators_a.py) | 138 |
| `dsg.ios_begin_tooth_removal` | Seleccionar diente del IOS | `DSG_OT_IOSBeginToothRemoval` | [blender/ios_tooth_edit.py](../blender/ios_tooth_edit.py) | 175 |
| `dsg.ios_cancel_tooth_removal` | Cancelar edición del diente | `DSG_OT_IOSCancelToothRemoval` | [blender/ios_tooth_edit.py](../blender/ios_tooth_edit.py) | 292 |
| `dsg.ios_circle_selection` | Seleccionar con círculo (C) | `DSG_OT_IOSCircleSelection` | [blender/ios_guided_selection.py](../blender/ios_guided_selection.py) | 302 |
| `dsg.ios_clear_selection` | Empezar selección de nuevo | `DSG_OT_IOSClearSelection` | [blender/ios_guided_selection.py](../blender/ios_guided_selection.py) | 286 |
| `dsg.ios_close_tooth_socket` | Cerrar hueco hacia dentro | `DSG_OT_IOSCloseToothSocket` | [blender/ios_tooth_edit.py](../blender/ios_tooth_edit.py) | 228 |
| `dsg.ios_retry_socket_boolean` | Reintentar booleana después del cierre | `DSG_OT_IOSRetrySocketBoolean` | [blender/ios_tooth_edit.py](../blender/ios_tooth_edit.py) | 324 |
| `dsg.ios_save_tooth_selection` | GUARDAR SELECCIÓN (P) | `DSG_OT_IOSSaveToothSelection` | [blender/ios_guided_selection.py](../blender/ios_guided_selection.py) | 227 |
| `dsg.ios_selection_mode` | Modo de selección | `DSG_OT_IOSSelectionMode` | [blender/ios_guided_selection.py](../blender/ios_guided_selection.py) | 271 |
| `dsg.ios_skip_tooth_removal` | SIGUIENTE | `DSG_OT_IOSSkipToothRemoval` | [blender/ios_skip_removal.py](../blender/ios_skip_removal.py) | 7 |
| `dsg.link_irrigation` | Link | `DSG_OT_LinkIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 833 |
| `dsg.measure_dicom_two_points` | Measure Two Points in DICOM MPR | `DSG_OT_MeasureDICOMTwoPoints` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 1442 |
| `dsg.measure_implant_to_dicom` | Measure Implant to DICOM | `DSG_OT_MeasureImplantToDICOM` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 1304 |
| `dsg.open_dicom_review` | Review DICOM | `DSG_OT_OpenDICOMReview` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 347 |
| `dsg.open_or_center_implant_mpr` | Implant MPR | `DSG_OT_OpenOrCenterImplantMPR` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 234 |
| `dsg.open_or_center_microscrew_mpr` | Microscrew MPR | `DSG_OT_OpenOrCenterMicroscrewMPR` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 283 |
| `dsg.optimize_frame_fem` | Optimize Frame | `DSG_OT_OptimizeFrameFEM` | [frame_structural.py](../frame_structural.py) | 1380 |
| `dsg.optimize_implant_position` | BUSCAR POSICIÓN | `DSG_OT_OptimizePosition` | [blender/implant_optimizer.py](../blender/implant_optimizer.py) | 432 |
| `dsg.optimize_implant_size` | COMPARAR TAMAÑOS | `DSG_OT_OptimizeSize` | [blender/implant_optimizer.py](../blender/implant_optimizer.py) | 438 |
| `dsg.optional_next` | SIGUIENTE | `DSG_OT_OptionalNext` | [blender/optional_next.py](../blender/optional_next.py) | 53 |
| `dsg.parallelize_implants` | Parallelize Implants to Master | `DSG_OT_ParallelizeImplants` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4146 |
| `dsg.perform_virtual_extraction` | REALIZAR OPERACIÓN BOOLEANA | `DSG_OT_PerformVirtualExtraction` | [blender/virtual_extraction.py](../blender/virtual_extraction.py) | 141 |
| `dsg.pick_lateral_opening_side` | Pick Lateral Opening Side | `DSG_OT_PickLateralOpeningSide` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2510 |
| `dsg.place_engrave_anchor` | Place Name on Surface | `DSG_OT_PlaceEngraveAnchor` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 1 |
| `dsg.play_animated_drills` | Play Drill Insertion | `DSG_OT_PlayAnimatedDrills` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1672 |
| `dsg.play_animated_microscrews` | Play Microscrew Insertion | `DSG_OT_PlayAnimatedMicroscrews` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2029 |
| `dsg.play_sequential_insertion_animation` | Play Screw, Drill and Implant Sequence | `DSG_OT_PlaySequentialInsertionAnimation` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2184 |
| `dsg.prepare_aligned_model` | Choose Insertion Axis from View | `DSG_OT_PrepareAlignedModel` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2862 |
| `dsg.prepare_and_create_drill_channels` | Prepare and Create Drill Channels | `DSG_OT_PrepareAndCreateDrillChannels` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3593 |
| `dsg.prepare_immediate_extraction` | Prepare Immediate Extraction | `DSG_OT_PrepareImmediateExtraction` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 2375 |
| `dsg.prepare_retention_unified` | PREPARAR MODELO RETENTIVO | `DSG_OT_PrepareRetentionUnified` | [blender/retention_finish.py](../blender/retention_finish.py) | 28 |
| `dsg.prepare_upper_cavities` | IDENTIFICAR SENOS Y CAVIDAD NASAL | `DSG_OT_PrepareUpperCavities` | [blender/upper_cavity_safety.py](../blender/upper_cavity_safety.py) | 216 |
| `dsg.preview_automatic_base_perimeter` | Preview Automatic Base Perimeter | `DSG_OT_PreviewAutomaticBasePerimeter` | [_guide_parts/02_implant_animation_geometry_b.py](../_guide_parts/02_implant_animation_geometry_b.py) | 1793 |
| `dsg.preview_geodesic_frame_fem` | Preview Surface-Geodesic Reinforcements (Experimental) | `DSG_OT_PreviewGeodesicFrameFEM` | [frame_structural.py](../frame_structural.py) | 1504 |
| `dsg.protect_drill_insertion` | Clear Drill Insertion Path | `DSG_OT_ProtectDrillInsertion` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 3284 |
| `dsg.rebuild_lateral_window_from_irrigation` | Legacy Lateral Window Rebuild (disabled) | `DSG_OT_RebuildLateralWindowFromIrrigation` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2799 |
| `dsg.refresh_roadmap_status` | Refresh Roadmap | `DSG_OT_RefreshRoadmapStatus` | [roadmap_module.py](../roadmap_module.py) | 1559 |
| `dsg.remove_last_dicom_measurement` | Delete Last DICOM Measurement | `DSG_OT_RemoveLastDICOMMeasurement` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 1547 |
| `dsg.remove_last_implant` | Delete Last Implant | `DSG_OT_RemoveLastImplant` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4053 |
| `dsg.remove_last_irrigation` | Delete | `DSG_OT_RemoveLastIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 1129 |
| `dsg.remove_last_microscrew` | Delete Last Microscrew | `DSG_OT_RemoveLastMicroscrew` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1846 |
| `dsg.remove_last_reinforcement` | Delete Last Connector | `DSG_OT_RemoveLastReinforcement` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2547 |
| `dsg.reopen_protected_neighbors` | Cambiar dientes vecinos | `DSG_OT_ReopenProtectedNeighbors` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 233 |
| `dsg.reset` | Reset Workflow | `DSG_OT_Reset` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2477 |
| `dsg.reset_current_step` | Back One Clinical Step | `DSG_OT_ResetCurrentStep` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2644 |
| `dsg.restore_immediate_tooth` | Restore Immediate Tooth | `DSG_OT_RestoreImmediateTooth` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 2416 |
| `dsg.review_upper_cavities` | REVISAR SENOS Y CAVIDAD NASAL | `DSG_OT_ReviewUpperCavities` | [blender/upper_cavity_safety.py](../blender/upper_cavity_safety.py) | 226 |
| `dsg.rotate_implant_inclination_plane` | Orientación del plano | `DSG_OT_RotateInclinationPlane` | [blender/implant_plane.py](../blender/implant_plane.py) | 360 |
| `dsg.run_boolean_preflight` | Check / Repair Meshes | `DSG_OT_RunBooleanPreflight` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2376 |
| `dsg.run_safety_failtests` | Ejecutar failtests DSG | `DSG_OT_RunSafetyFailtests` | [runtime_bootstrap.py](../runtime_bootstrap.py) | 193 |
| `dsg.runtime_preflight` |  | `DSG_OT_RuntimePreflight` | [runtime_bootstrap.py](../runtime_bootstrap.py) | 176 |
| `dsg.select_axis` | Select Axis | `DSG_OT_SelectAxis` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2986 |
| `dsg.select_mpr_implant` | Select Implant for MPR | `DSG_OT_SelectMPRImplant` | [_guide_parts/01_workflow_state_mpr_objects_b.py](../_guide_parts/01_workflow_state_mpr_objects_b.py) | 199 |
| `dsg.select_retention_preset` | Select Retention Profile | `DSG_OT_SelectRetentionPreset` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3012 |
| `dsg.set_axis_from_fdi` | Propose Implant Axis from FDI | `DSG_OT_SetAxisFromFDI` | [roadmap_module.py](../roadmap_module.py) | 442 |
| `dsg.set_irrigation_cylinder_channel_mode` | Set cylinder channel mode | `DSG_OT_SetIrrigationCylinderChannelMode` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 61 |
| `dsg.set_parallel_master` | Use Selected as Master | `DSG_OT_SetParallelMaster` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4126 |
| `dsg.show_animated_drill_start` | Show Start Position | `DSG_OT_ShowAnimatedDrillStart` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1752 |
| `dsg.show_animated_drill_stop` | Show Maximum Insertion | `DSG_OT_ShowAnimatedDrillStop` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1765 |
| `dsg.show_animated_microscrew_start` | Show Microscrew Start Position | `DSG_OT_ShowAnimatedMicroscrewStart` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2119 |
| `dsg.show_animated_microscrew_stop` | Show Microscrew Final Seat | `DSG_OT_ShowAnimatedMicroscrewStop` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2137 |
| `dsg.show_exact_irrigation_lumen_diagnostic` | Show Checked Water Lumen | `DSG_OT_ShowExactIrrigationLumenDiagnostic` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 379 |
| `dsg.show_safety_contacts` | ALERTA DE SEGURIDAD | `DSG_OT_ShowSafetyContacts` | [blender/safety_alerts.py](../blender/safety_alerts.py) | 96 |
| `dsg.simulate_irrigation_flow` | Update Solid Water Flow | `DSG_OT_SimulateIrrigationFlow` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 2151 |
| `dsg.skip_irrigation` | Skip Irrigation | `DSG_OT_SkipIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 1201 |
| `dsg.skip_patient_name` | Continue Without Name | `DSG_OT_SkipPatientName` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 155 |
| `dsg.skip_reinforcement` | Skip Reinforcement Connectors | `DSG_OT_SkipReinforcement` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2566 |
| `dsg.start_drawing` | Draw / Continue Outline | `DSG_OT_StartDrawing` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3679 |
| `dsg.start_irrigation` | Draw Irrigation Channel | `DSG_OT_StartIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 218 |
| `dsg.start_irrigation_from_points` | Irrigation Preview from Points | `DSG_OT_StartIrrigationFromPoints` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 181 |
| `dsg.start_mcp_bridge` | Start MCP Bridge | `DSG_OT_StartMCPBridge` | [roadmap_module.py](../roadmap_module.py) | 1522 |
| `dsg.start_microscrew` | Select 3 Microscrew Points | `DSG_OT_StartMicroscrew` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1488 |
| `dsg.start_reinforcement` | Draw Reinforcement Chain | `DSG_OT_StartReinforcement` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2295 |
| `dsg.stop_animated_drills` | Stop Drill Animation | `DSG_OT_StopAnimatedDrills` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1698 |
| `dsg.stop_animated_microscrews` | Stop Microscrew Animation | `DSG_OT_StopAnimatedMicroscrews` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2065 |
| `dsg.stop_mcp_bridge` | Stop MCP Bridge | `DSG_OT_StopMCPBridge` | [roadmap_module.py](../roadmap_module.py) | 1532 |
| `dsg.stop_sequential_insertion_animation` | Stop Insertion Sequence | `DSG_OT_StopSequentialInsertionAnimation` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2225 |
| `dsg.toggle_animated_drills_visibility` | Show or Hide Animated Drills | `DSG_OT_ToggleAnimatedDrillsVisibility` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 1721 |
| `dsg.toggle_animated_microscrews_visibility` | Show or Hide Animated Microscrews | `DSG_OT_ToggleAnimatedMicroscrewsVisibility` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2092 |
| `dsg.toggle_blockout_visibility` | Show/Hide Model | `DSG_OT_ToggleBlockoutVisibility` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 447 |
| `dsg.toggle_contour_point_edit` | Edit Frame Points | `DSG_OT_ToggleContourPointEdit` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3797 |
| `dsg.toggle_extraction_tooth_smoothing` | Suavizado del diente a extraer | `DSG_OT_ToggleExtractionSmoothing` | [blender/extraction_extension.py](../blender/extraction_extension.py) | 110 |
| `dsg.toggle_guide_visibility` | Show/Hide Guide | `DSG_OT_ToggleGuideVisibility` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 468 |
| `dsg.toggle_implant_inclination_planes` | Mostrar/ocultar planos del implante | `DSG_OT_ToggleInclinationPlanes` | [blender/implant_plane.py](../blender/implant_plane.py) | 393 |
| `dsg.toggle_implant_parallel_lock` | Lock Implant for Parallelization | `DSG_OT_ToggleImplantParallelLock` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 4090 |
| `dsg.toggle_irrigation_implant_seal` | Open / Seal Implant Irrigation | `DSG_OT_ToggleIrrigationImplantSeal` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 94 |
| `dsg.toggle_lateral_opening` | Lateral Opening (moved) | `DSG_OT_ToggleLateralOpening` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 2274 |
| `dsg.toggle_mpr_plane` | Mostrar/ocultar MPR | `DSG_OT_ToggleMPRPlane` | [blender/mpr_view.py](../blender/mpr_view.py) | 199 |
| `dsg.toggle_protected_neighbor` | Conservar diente vecino | `DSG_OT_ToggleProtectedNeighbor` | [blender/protected_neighbors.py](../blender/protected_neighbors.py) | 164 |
| `dsg.toggle_sequential_insertion_visibility` | Show or Hide Screws, Drills and Implants | `DSG_OT_ToggleSequentialInsertionVisibility` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2265 |
| `dsg.undo_virtual_extraction` | Restaurar diente | `DSG_OT_UndoVirtualExtraction` | [blender/virtual_extraction.py](../blender/virtual_extraction.py) | 241 |
| `dsg.update_confirm_irrigation` | Confirm | `DSG_OT_UpdateConfirmIrrigation` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 529 |
| `dsg.update_engrave_preview` | Update Preview | `DSG_OT_UpdateEngravePreview` | [_guide_parts/08_export_final_ui_registration.py](../_guide_parts/08_export_final_ui_registration.py) | 51 |
| `dsg.update_final_animation` | Update Final Animation | `DSG_OT_UpdateFinalAnimation` | [_guide_parts/07_reinforcement_animation.py](../_guide_parts/07_reinforcement_animation.py) | 2123 |
| `dsg.update_irrigation_preview` | Update Walls from Path | `DSG_OT_UpdateIrrigationPreview` | [_guide_parts/06_irrigation_b.py](../_guide_parts/06_irrigation_b.py) | 330 |
| `dsg.update_microscrew_from_visual` | Update Microscrew From Visual | `DSG_OT_UpdateMicroscrewFromVisual` | [_guide_parts/05_frame_microscrews_sleeves_drill.py](../_guide_parts/05_frame_microscrews_sleeves_drill.py) | 1723 |
| `dsg.use_selected_ios_model` | Use Selected IOS Model | `DSG_OT_UseSelectedIOSModel` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 2814 |
| `dsg.validate_blockout_seating` | Validate Guide Seating | `DSG_OT_ValidateBlockoutSeating` | [_guide_parts/04_properties_clinical_operators.py](../_guide_parts/04_properties_clinical_operators.py) | 3423 |
| `dsg.voxel_remesh_restore` | Mallas originales | `DSG_OT_VoxelRemeshRestore` | [cbct_dental_module.py](../cbct_dental_module.py) | 2163 |
| `dsg.voxel_remesh_segmented` | Remesh vóxel | `DSG_OT_VoxelRemeshSegmented` | [cbct_dental_module.py](../cbct_dental_module.py) | 2121 |
| `dsg_suite.accept_fdi_select_teeth` | FDI correcto · elegir dientes | `DSG_SUITE_OT_AcceptFDIAndSelectTeeth` | [core.py](../core.py) | 1501 |
| `dsg_suite.back_workflow` | Atrás | `DSG_SUITE_OT_BackWorkflow` | [core.py](../core.py) | 3458 |
| `dsg_suite.build_immediate_arch_models` | Siguiente · crear modelos alveolares | `DSG_SUITE_OT_BuildImmediateArchModels` | [core.py](../core.py) | 1603 |
| `dsg_suite.change_route` | Cambiar ruta | `DSG_SUITE_OT_ChangeRoute` | [core.py](../core.py) | 1074 |
| `dsg_suite.choose_patient_folder` | Elegir paciente | `DSG_SUITE_OT_ChoosePatientFolder` | [core.py](../core.py) | 968 |
| `dsg_suite.confirm_immediate_models` | Confirmar | `DSG_SUITE_OT_ConfirmImmediateModels` | [core.py](../core.py) | 1668 |
| `dsg_suite.confirm_ios_postextraction` | Confirmar IOS postextracción | `DSG_SUITE_OT_ConfirmIOSPostExtraction` | [core.py](../core.py) | 3027 |
| `dsg_suite.confirm_simple_stl` | Confirmar arcadas y alinear | `DSG_SUITE_OT_ConfirmSimpleSTL` | [core.py](../core.py) | 1279 |
| `dsg_suite.fix_immediate_extraction_selection` | Fijar dientes de extracción | `DSG_SUITE_OT_FixImmediateExtractionSelection` | [core.py](../core.py) | 1567 |
| `dsg_suite.install_engines_core` |  | `DSG_SUITE_OT_InstallEnginesCore` | [core.py](../core.py) | 4109 |
| `dsg_suite.load_patient_cbct` | Cargar CBCT del paciente | `DSG_SUITE_OT_LoadPatientCBCT` | [core.py](../core.py) | 1060 |
| `dsg_suite.prepare_ios_postextraction` | Preparar selección IOS postextracción | `DSG_SUITE_OT_PrepareIOSPostExtraction` | [core.py](../core.py) | 1941 |
| `dsg_suite.recover_immediate_inputs` | Recover Immediate Inputs | `DSG_SUITE_OT_RecoverImmediateInputs` | [core.py](../core.py) | 3262 |
| `dsg_suite.restart_alignment` | Reiniciar alineamiento | `DSG_SUITE_OT_RestartAlignment` | [core.py](../core.py) | 3550 |
| `dsg_suite.restart_dicom` | Reiniciar DICOM | `DSG_SUITE_OT_RestartDICOM` | [core.py](../core.py) | 3519 |
| `dsg_suite.restart_dsg` | Reiniciar DSG | `DSG_SUITE_OT_RestartDSG` | [core.py](../core.py) | 3575 |
| `dsg_suite.restore_ios_preextraction` | Restaurar IOS preextracción | `DSG_SUITE_OT_RestoreIOSPreExtraction` | [core.py](../core.py) | 3174 |
| `dsg_suite.set_stage` | Open module | `DSG_SUITE_OT_SetStage` | [core.py](../core.py) | 3710 |
| `dsg_suite.start_immediate_route` | Implante inmediato | `DSG_SUITE_OT_StartImmediateRoute` | [core.py](../core.py) | 1371 |
| `dsg_suite.start_simple_route` | Implante simple | `DSG_SUITE_OT_StartSimpleRoute` | [core.py](../core.py) | 1238 |
| `dsg_suite.toggle_antagonist` | Toggle Antagonist | `DSG_SUITE_OT_ToggleAntagonist` | [core.py](../core.py) | 3781 |
| `dsg_suite.use_selected_ios` | Use selected IOS | `DSG_SUITE_OT_UseSelectedIOS` | [core.py](../core.py) | 3749 |


## Axial radial web V2 (2026-10-21)

The Optimize Frame action now dispatches to `blender/axial_web_pipeline.py` for new snapshots. See `docs/AXIAL_RADIAL_WEB.md`. The V1 worker and review paths remain available for their original requests. `axial_radial_web.py` builds the shared distance graph, `blender/axial_design_sheet.py` constructs the IOS-guided extrados, `axial_capsule.py` and `blender/axial_implicit_web.py` form the shared volume, and `blender/axial_web_mesh.py` verifies the final geometry. `axial_web_contract.py` binds the inputs, artifacts and receipts.
