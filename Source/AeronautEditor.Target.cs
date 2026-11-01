using UnrealBuildTool;
using System.Collections.Generic;
public class AeronautEditorTarget : TargetRules
{
    public AeronautEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("Aeronaut");
        ExtraModuleNames.Add("AeronautTools");
    }
}

