# Preferred rules for design

1. Keep the content of one section in one viewheight, don't merge two sections together in 1 vh or expand one section beyond 1vh and lengthy so that user needs to scroll vertically to see it ( I want every content shown in screen to have one chunk visible in 1vh and 1vw)
2. user the font Inter and Lora as mentioned in the design system of this doc ./design-system.md
3. keep the font size, font weight, line height same as mentioned in design-system, no surprises should come, even if a image is provided and asked to match its design exactly, you will not blindly copy everything in the image, you will make sure you adapt its information heirarchy but keep following the design system of this project only be it font, colors, card, tabs or any other component, if that component is not present in the current project the you will create and design it as per the design system of this project, never ever will you blindly match any image or SS that's given for you to copy, always the goal will be to copy its information heirarchy, structure but keep the design components of this project
4. There will be changes introduced that won't match the figma design, you will implement it but at the same time highlight the conflicts with the existing design-system if there are any before moving ahead and take the user's confirmation before implementing it.
5. the changes should look coherent across this project, there can't be two different types of tab switch components used, they can't be two different types of card, everything present and everything that's going to be added should merge well together while abiding to the design-system.md doc

# preffered rules for Code

1. Keep the mode modular and reusable
2. follow the best coding practices for structure of the code
3. Keep decoupled components and functions
4. use hooks for optimum data flow
