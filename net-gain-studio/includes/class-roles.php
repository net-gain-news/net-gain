<?php
/**
 * Custom roles and the capability grants that gate both the CPT REST endpoints
 * (via capability_type + map_meta_cap) and our own net-gain/v1 routes.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Roles {

	const SERVICE_ROLE = 'ng_service';
	const TALENT_ROLE   = 'ng_talent';

	// [ singular, plural ] capability_type pairs used by our three CPTs.
	const CPT_TYPES = array(
		'ng_vertical' => 'ng_verticals',
		'ng_show'     => 'ng_shows',
		'ng_episode'  => 'ng_episodes',
	);

	public static function register_roles() {
		if ( ! get_role( self::SERVICE_ROLE ) ) {
			add_role( self::SERVICE_ROLE, 'Net Gain Service Account', array( 'read' => true ) );
		}
		if ( ! get_role( self::TALENT_ROLE ) ) {
			add_role( self::TALENT_ROLE, 'Net Gain Talent', array( 'read' => true, 'upload_files' => true ) );
		}
	}

	/**
	 * Administrator gets full CRUD on all three CPTs. The service account (Python,
	 * via Application Password) gets full CRUD on ng_show/ng_episode but no delete
	 * capability and no access to ng_vertical at all (it never touches templates) -
	 * least-privilege per Spec Section 3.3's general posture on studio-owned secrets
	 * and access.
	 */
	public static function grant_capabilities() {
		$admin = get_role( 'administrator' );
		$service = get_role( self::SERVICE_ROLE );

		foreach ( self::CPT_TYPES as $singular => $plural ) {
			if ( $admin ) {
				foreach ( self::full_capability_list( $plural ) as $cap ) {
					$admin->add_cap( $cap );
				}
			}

			if ( $service && 'ng_vertical' !== $singular ) {
				foreach ( self::operational_capability_list( $plural ) as $cap ) {
					$service->add_cap( $cap );
				}
			}
		}
	}

	private static function full_capability_list( $plural ) {
		return array(
			"edit_{$plural}",
			"edit_others_{$plural}",
			"edit_published_{$plural}",
			"edit_private_{$plural}",
			"publish_{$plural}",
			"create_{$plural}",
			"read_private_{$plural}",
			"delete_{$plural}",
			"delete_others_{$plural}",
			"delete_published_{$plural}",
			"delete_private_{$plural}",
		);
	}

	// Same as full_capability_list() minus every delete_* capability.
	private static function operational_capability_list( $plural ) {
		return array(
			"edit_{$plural}",
			"edit_others_{$plural}",
			"edit_published_{$plural}",
			"edit_private_{$plural}",
			"publish_{$plural}",
			"create_{$plural}",
			"read_private_{$plural}",
		);
	}
}
