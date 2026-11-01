# Visual assets

- `sekiro.ico` is the original repository icon, unchanged (red kanji).
- `assets/sekiro-original.ico` is a byte-for-byte copy used by the window.
- `assets/sekiro-teleport.png` is a transparent logo made with the built-in image generation tool from the user's supplied logo reference. Its subtitle reads TELEPORT.
- `assets/menu-background.png` was made with the built-in image editing tool from the user's supplied inventory screenshot: equipment and text were removed to make a usable menu background. It is a reconstruction, not an extraction of the game's textures or a claim of pixel-identical game UI.
- `assets/compact-background.png` was made with the built-in image editing tool from that background: a portrait sheet of aged paper and an ornamental frame, with the old game-menu compartments removed. The utility now has its own compact layout.
- Brushes are sampled from `menu-background.png` by the renderer. Text, inputs, records, focus, and actions are live application controls.
- Version 2.2 retains exactly the 2.1 source brush crops and RGB pixels. `brush_texture.py` adjusts only alpha using an estimate of the paper behind the ink. This corrects rectangular seams without replacing the brush artwork.

The visual references are from Sekiro: Shadows Die Twice. This is an unofficial fan tool, not an official FromSoftware or Activision product. No game archives, executable code or fonts are included.

## Logo edit prompt

Retain the large word SEKIRO in distressed pale silver metal, chipped sharp serif edges and rusty gold patina. Replace SHADOWS DIE TWICE with the exact word TELEPORT in weathered gold serif lettering, centered beneath SEKIRO. Remove TM. Transparent background, no other text.

## Background edit prompt

Clean up the supplied 1920×1080 Sekiro inventory screenshot. Preserve the composition, gray-brown rice-paper fibers, wrinkles, folds, grime, ragged black outer cloth, wooden antique gold frame and ornate decorations. Remove all text, numbers, items, equipment icons, meters, controller prompts and slot backings. Inpaint them with continuous aged paper. Keep the four top brush strokes, the small section-heading swashes, the large weathered description panel on the right, its ink rules and top brush, and the bottom status-panel backgrounds. No new text, icons or logos. Landscape 16:9. Preserve the menu artwork rather than redesigning it.

## Compact background edit prompt

Turn the existing Sekiro-style background into a portrait 6:7 sheet. Preserve black torn cloth, narrow wooden frame with antique gold ornamental corners, and gray-brown weathered fibrous paper, folds, scratches and patina. Make the interior one continuous empty sheet. Remove all brush strokes, compartments, rules and status panels. No text, controls, icons or logos. Match the reference's muted gray-brown palette and keep the central paper readable. Built-in image editing tool used; no game files were extracted.
