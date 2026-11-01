using UnrealBuildTool;
public class Aeronaut : ModuleRules
{
    public Aeronaut(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "ProceduralMeshComponent"
        });
        PrivateDependencyModuleNames.AddRange(new string[] { "RHI", "RenderCore", "Renderer" });
    }
}
