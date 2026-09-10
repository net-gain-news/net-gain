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

		// Phase 6 (website publishing): the publish-website REST route creates real
		// WordPress Posts (Seriously Simple Podcasting's "podcast" CPT, which uses
		// the standard 'post' capability_type like any ordinary plugin CPT), Pages
		// (the show hub pages), and "series" taxonomy terms - none of which are
		// covered by our own ng_show/ng_episode capability_type above. Administrator
		// already has all of these by default; the service account needs them
		// granted explicitly, still short of full delete/admin capabilities.
		if ( $service ) {
			foreach ( array( 'edit_posts', 'edit_others_posts', 'publish_posts', 'edit_pages', 'edit_others_pages', 'publish_pages', 'manage_categories' ) as $cap ) {
				$service->add_cap( $cap );
			}

			// Phase 8 (image pipeline): uploading rendered episode art to the media
			// library via POST /wp/v2/media requires upload_files, which nothing had
			// granted the service account until now (only the Talent role had it).
			$service->add_cap( 'upload_files' );
		}
	}

	/**
	 * grant_capabilities() only ever ran from Net_Gain_Activator::activate() -
	 * fine for a fresh install, but it means a capability added to the code
	 * (like upload_files above) silently does nothing on an already-installed
	 * live site until something re-triggers it. This re-runs role/capability
	 * setup once per version bump, generically, rather than requiring a manual
	 * deactivate/reactivate every time a phase needs a new capability.
	 */
	public static function maybe_upgrade() {
		if ( get_option( 'ng_db_version' ) === NET_GAIN_VERSION ) {
			return;
		}
		self::register_roles();
		self::grant_capabilities();
		update_option( 'ng_db_version', NET_GAIN_VERSION );
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
