using UnrealBuildTool;
public class AeronautTools : ModuleRules {
    public AeronautTools(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[]{"Core","CoreUObject","Engine"});
        PrivateDependencyModuleNames.AddRange(new[]{"UnrealEd","Landscape","LandscapeEditor","Aeronaut","AssetTools","MeshDescription","StaticMeshDescription"});
    }
}
